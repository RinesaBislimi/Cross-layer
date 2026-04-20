"""Backend alert rule evaluation.

Called after every incident-generation batch.  Loads all enabled AlertRule
rows, checks each rule against the new incidents, fires email / webhook once
per rule per cooldown window (default 5 min), and updates trigger_count.
"""

import json as _json
import logging
import smtplib
import threading
import urllib.request as _req
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import List, Optional

from sqlalchemy.orm import Session

from ..config import get_settings
from ..models.alert_rule import AlertRule
from ..models.incidents import Incident

logger = logging.getLogger(__name__)

_COOLDOWN_MINUTES = 5          # minimum minutes between repeated fires for the same rule
_SEV_SCORE = {"critical": 0.90, "high": 0.75, "medium": 0.50, "low": 0.25}
_SEV_COLOR = {
    "critical": "#dc2626",
    "high":     "#ea580c",
    "medium":   "#ca8a04",
    "low":      "#16a34a",
}


def _sev_score(sev):
    # type: (Optional[str]) -> float
    return _SEV_SCORE.get((sev or "").lower(), 0.25)


# ── Rule matching ─────────────────────────────────────────────────────────────

def _rule_matches(rule, incident):
    # type: (AlertRule, Incident) -> bool
    sev      = (incident.severity or "").lower()
    attrs    = incident.attributes or {}
    layers   = attrs.get("layers", []) if isinstance(attrs, dict) else []
    inc_type = (incident.type or "").lower()

    # Optional layer filter
    if rule.layer:
        if rule.layer not in layers:
            return False

    cond = rule.condition
    if cond == "any_anomaly":       return True
    if cond == "critical_severity": return sev == "critical"
    if cond == "high_severity":     return sev in ("high", "critical")
    if cond == "cross_layer":       return len(layers) > 1 or "cross-layer" in inc_type
    if cond == "entity_repeat":     return bool(incident.entity)
    return False


# ── Email helpers ─────────────────────────────────────────────────────────────

def _build_email(rule, incidents, now):
    # type: (AlertRule, List[Incident], datetime) -> MIMEMultipart
    count            = len(incidents)
    condition_label  = rule.condition.replace("_", " ").title()
    subject          = "CrossLayer Alert: %s (%d incident%s)" % (
        rule.name, count, "s" if count != 1 else ""
    )

    # HTML incident rows (cap at 10)
    rows_html = ""
    rows_text = ""
    for inc in incidents[:10]:
        attrs     = inc.attributes or {}
        layers    = attrs.get("layers", []) if isinstance(attrs, dict) else []
        layer_str = ", ".join(layers) if layers else "unknown"
        sev       = inc.severity or "unknown"
        color     = _SEV_COLOR.get(sev, "#64748b")
        rows_html += (
            "<tr>"
            "<td style='padding:6px 8px;border-bottom:1px solid #e2e8f0'>%s</td>"
            "<td style='padding:6px 8px;border-bottom:1px solid #e2e8f0;"
            "color:%s;font-weight:600'>%s</td>"
            "<td style='padding:6px 8px;border-bottom:1px solid #e2e8f0'>%s</td>"
            "<td style='padding:6px 8px;border-bottom:1px solid #e2e8f0'>%s</td>"
            "</tr>"
        ) % (inc.type or "unknown", color, sev, inc.entity or "—", layer_str)
        rows_text += "  - %s | %s | entity: %s | layers: %s\n" % (
            inc.type or "unknown", sev, inc.entity or "—", layer_str
        )

    if count > 10:
        rows_html += (
            "<tr><td colspan='4' style='padding:6px 8px;color:#64748b;"
            "font-style:italic'>… and %d more</td></tr>"
        ) % (count - 10)
        rows_text += "  … and %d more\n" % (count - 10)

    html_body = """
<html><body style="font-family:sans-serif;color:#1e293b;max-width:600px;margin:0 auto">
  <div style="background:#dc2626;padding:18px 24px;border-radius:8px 8px 0 0">
    <h2 style="color:#fff;margin:0;font-size:1rem">&#x1F6A8; CrossLayer Security Alert</h2>
  </div>
  <div style="background:#f8fafc;border:1px solid #e2e8f0;border-top:none;
              padding:20px 24px;border-radius:0 0 8px 8px">
    <p style="margin:0 0 8px"><strong>Rule:</strong> {name}</p>
    <p style="margin:0 0 16px"><strong>Condition triggered:</strong> {cond}</p>
    <p style="margin:0 0 8px"><strong>{count} matching incident{plural}:</strong></p>
    <table style="width:100%;border-collapse:collapse;font-size:.82rem;
                  background:#fff;border:1px solid #e2e8f0;border-radius:6px">
      <thead>
        <tr style="background:#f1f5f9">
          <th style="padding:7px 8px;text-align:left">Type</th>
          <th style="padding:7px 8px;text-align:left">Severity</th>
          <th style="padding:7px 8px;text-align:left">Entity</th>
          <th style="padding:7px 8px;text-align:left">Layers</th>
        </tr>
      </thead>
      <tbody>{rows}</tbody>
    </table>
    <p style="margin:16px 0 0;font-size:.78rem;color:#94a3b8">
      Triggered at {ts} — CrossLayer Security System
    </p>
  </div>
</body></html>""".format(
        name=rule.name,
        cond=condition_label,
        count=count,
        plural="s" if count != 1 else "",
        rows=rows_html,
        ts=now.strftime("%Y-%m-%d %H:%M:%S UTC"),
    )

    text_body = (
        "CrossLayer Alert: %s\n"
        "Condition: %s\n"
        "Time: %s\n\n"
        "%d matching incident(s):\n%s"
    ) % (rule.name, condition_label, now.strftime("%Y-%m-%d %H:%M:%S UTC"), count, rows_text)

    cfg     = get_settings()
    from_addr = cfg.SMTP_FROM or cfg.SMTP_USER

    msg             = MIMEMultipart("alternative")
    msg["Subject"]  = subject
    msg["From"]     = from_addr
    msg["To"]       = rule.notify_target
    msg.attach(MIMEText(text_body, "plain"))
    msg.attach(MIMEText(html_body, "html"))
    return msg


def _send_email_sync(rule, incidents, now):
    # type: (AlertRule, List[Incident], datetime) -> None
    cfg = get_settings()
    if not cfg.SMTP_USER or not cfg.SMTP_PASS or cfg.SMTP_USER == "your_gmail@gmail.com":
        logger.warning("SMTP not configured — skipping email for rule '%s'", rule.name)
        return
    msg = _build_email(rule, incidents, now)
    try:
        with smtplib.SMTP_SSL(cfg.SMTP_HOST, cfg.SMTP_PORT, timeout=10) as srv:
            srv.login(cfg.SMTP_USER, cfg.SMTP_PASS)
            srv.sendmail(cfg.SMTP_FROM or cfg.SMTP_USER, rule.notify_target, msg.as_string())
        logger.info(
            "Alert email sent → %s | rule '%s' | %d incident(s)",
            rule.notify_target, rule.name, len(incidents),
        )
    except Exception as exc:
        logger.error("Alert email failed for rule '%s': %s", rule.name, exc)


def _send_webhook(url, payload):
    # type: (str, dict) -> None
    try:
        data = _json.dumps(payload).encode()
        req  = _req.Request(
            url, data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        _req.urlopen(req, timeout=5)
    except Exception as exc:
        logger.warning("Webhook POST failed (%s): %s", url, exc)


# ── Public API ────────────────────────────────────────────────────────────────

def evaluate_and_fire(db, incidents):
    # type: (Session, List[Incident]) -> int
    """Evaluate enabled alert rules against *incidents*.

    - Skips rules inside their cooldown window.
    - For each matching rule fires email (sync in thread) or webhook (daemon thread).
    - Updates trigger_count and last_fired_at, then commits once.
    - Returns the number of rules that actually fired.
    """
    if not incidents:
        return 0

    try:
        rules = db.query(AlertRule).filter(AlertRule.enabled.is_(True)).all()
    except Exception as exc:
        logger.error("Could not load alert rules from DB: %s", exc)
        return 0

    now      = datetime.utcnow()
    cooldown = timedelta(minutes=_COOLDOWN_MINUTES)
    fired    = 0

    logger.info(
        "evaluate_and_fire: checking %d rule(s) against %d incident(s)",
        len(rules), len(incidents),
    )

    for rule in rules:
        # Cooldown guard
        if rule.last_fired_at and (now - rule.last_fired_at) < cooldown:
            remaining = int((cooldown - (now - rule.last_fired_at)).total_seconds() / 60)
            logger.info(
                "Rule '%s' skipped — cooldown active (%d min remaining)", rule.name, remaining
            )
            continue

        matching = [inc for inc in incidents if _rule_matches(rule, inc)]
        logger.info(
            "Rule '%s' (cond=%s layer=%r): %d/%d incidents matched",
            rule.name, rule.condition, rule.layer or "all", len(matching), len(incidents),
        )
        if not matching:
            continue

        # Fire in background so we don't block the HTTP response
        if rule.notify_method == "email" and rule.notify_target:
            # Copy data needed for thread (ORM objects may expire after commit)
            snap = list(matching)
            t    = threading.Thread(
                target=_send_email_sync, args=(rule, snap, now), daemon=True
            )
            t.start()

        elif rule.notify_method == "webhook" and rule.notify_target:
            payload = {
                "rule":          rule.name,
                "condition":     rule.condition,
                "matched_count": len(matching),
                "timestamp":     now.isoformat(),
            }
            t = threading.Thread(
                target=_send_webhook, args=(rule.notify_target, payload), daemon=True
            )
            t.start()

        # Update stats
        rule.trigger_count = (rule.trigger_count or 0) + len(matching)
        rule.last_fired_at = now
        fired += 1

    if fired:
        try:
            db.commit()
        except Exception as exc:
            logger.error("Could not persist trigger counts: %s", exc)
            db.rollback()

    return fired
