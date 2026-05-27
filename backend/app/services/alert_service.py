
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

_COOLDOWN_MINUTES = 5
_SEV_SCORE = {"critical": 0.90, "high": 0.75, "medium": 0.50, "low": 0.25}

def _sev_score(sev):
    return _SEV_SCORE.get((sev or "").lower(), 0.25)

def _rule_matches(rule, incident):
    sev      = (incident.severity or "").lower()
    attrs    = incident.attributes or {}
    layers   = attrs.get("layers", []) if isinstance(attrs, dict) else []
    inc_type = (incident.type or "").lower()

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

def _max_severity(incidents):
    for s in ("critical", "high", "medium", "low"):
        if any((inc.severity or "").lower() == s for inc in incidents):
            return s
    return "unknown"

def _sev_counts(incidents):
    counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    for inc in incidents:
        s = (inc.severity or "").lower()
        if s in counts:
            counts[s] += 1
    return counts

def _build_email(rule, incidents, now, is_test=False):
    count           = len(incidents)
    condition_label = rule.condition.replace("_", " ").title()
    max_sev         = _max_severity(incidents) if incidents else "unknown"
    sev_counts_map  = _sev_counts(incidents)
    ts_short        = now.strftime("%b %d, %H:%M UTC")
    ts_full         = now.strftime("%Y-%m-%d %H:%M:%S")
    test_prefix     = "[TEST] " if is_test else ""

    subject = "%sCrossLayer Alert: %s -- %d incident%s detected" % (
        test_prefix, rule.name, count, "s" if count != 1 else ""
    )

    sev_cells_html = ""
    for sev, label in (("critical", "Critical"), ("high", "High"),
                       ("medium", "Medium"), ("low", "Low")):
        n = sev_counts_map[sev]
        sev_cells_html += (
            "<td style='text-align:center;padding:0 4px'>"
            "<div style='border:1px solid #e2e8f0;border-radius:6px;padding:10px 6px'>"
            "<div style='font-size:1.25rem;font-weight:800;color:#0f172a;line-height:1'>%d</div>"
            "<div style='font-size:0.6rem;text-transform:uppercase;letter-spacing:0.08em;"
            "color:#64748b;font-weight:600;margin-top:3px'>%s</div>"
            "</div></td>"
        ) % (n, label)

    rows_html  = ""
    plain_list = ""
    for inc in incidents[:15]:
        attrs     = inc.attributes or {}
        layers    = attrs.get("layers", []) if isinstance(attrs, dict) else []
        layer_str = ", ".join(layers) if layers else "-"
        sev       = (inc.severity or "unknown").upper()
        etype     = (inc.type or "Unknown").replace("_", " ").title()
        entity    = inc.entity or "-"

        rows_html += (
            "<tr style='border-bottom:1px solid #f1f5f9'>"
            "<td style='padding:9px 10px 9px 0;font-size:0.78rem;font-weight:600;"
            "color:#0f172a;vertical-align:top'>%s</td>"
            "<td style='padding:9px 10px;font-size:0.75rem;color:#475569;"
            "vertical-align:top'>%s</td>"
            "<td style='padding:9px 10px;font-size:0.72rem;color:#475569;"
            "vertical-align:top'>%s</td>"
            "<td style='padding:9px 0 9px 10px;font-size:0.72rem;font-weight:700;"
            "color:#0f172a;vertical-align:top;white-space:nowrap'>%s</td>"
            "</tr>"
        ) % (etype, entity, layer_str, sev)

        plain_list += "  [%s] %s  entity:%s  layers:%s\n" % (sev, etype, entity, layer_str)

    trunc_note = ""
    if count > 15:
        trunc_note = "(showing 15 of %d)" % count
        rows_html += (
            "<tr><td colspan='4' style='padding:9px 0;font-size:0.72rem;"
            "color:#94a3b8;font-style:italic'>... and %d more incidents</td></tr>"
        ) % (count - 15)
        plain_list += "  ... and %d more\n" % (count - 15)

    test_row_html = ""
    if is_test:
        test_row_html = (
            "<tr><td style='background:#fff;padding:0 28px 20px'>"
            "<div style='border:1px dashed #cbd5e1;border-radius:6px;padding:10px 14px;"
            "font-size:0.75rem;color:#64748b;text-align:center'>"
            "This is a test notification. No real threat was detected."
            "</div></td></tr>"
        )

    html_body = """\
<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
</head>
<body style="margin:0;padding:0;background:#f1f5f9;
             font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Arial,sans-serif">

<div style="display:none;max-height:0;overflow:hidden;color:#f1f5f9">
  {test_pfx}CrossLayer Alert: {rule_name} -- {count} incident{plural} at {ts_short}
</div>

<table width="100%%" cellpadding="0" cellspacing="0"
       style="background:#f1f5f9;padding:32px 16px">
<tr><td align="center">
<table width="580" cellpadding="0" cellspacing="0" style="max-width:580px;width:100%%">

  <!-- HEADER -->
  <tr>
    <td style="background:#0f172a;border-radius:8px 8px 0 0;padding:22px 28px 20px">
      <table width="100%%" cellpadding="0" cellspacing="0"><tr>
        <td style="vertical-align:middle">
          <div style="color:#f8fafc;font-size:0.9rem;font-weight:700;
                       letter-spacing:-0.01em">CrossLayer</div>
          <div style="color:#475569;font-size:0.65rem;margin-top:2px;
                       text-transform:uppercase;letter-spacing:0.06em">
            Security Platform
          </div>
        </td>
        <td style="text-align:right;vertical-align:middle">
          <span style="border:1px solid #334155;color:#94a3b8;font-size:0.65rem;
                        font-weight:600;letter-spacing:0.06em;text-transform:uppercase;
                        padding:4px 12px;border-radius:4px">{label_tag}</span>
        </td>
      </tr></table>

      <div style="margin-top:20px;padding-top:18px;border-top:1px solid #1e293b">
        <div style="color:#f8fafc;font-size:1.05rem;font-weight:700;line-height:1.3">
          {alert_title}
        </div>
        <div style="color:#64748b;font-size:0.78rem;margin-top:5px">
          Rule: <span style="color:#94a3b8">{rule_name}</span>
          &nbsp;&middot;&nbsp;{ts_short}
        </div>
      </div>
    </td>
  </tr>

  <!-- SUMMARY STRIP -->
  <tr>
    <td style="background:#1e293b;padding:14px 28px">
      <table width="100%%" cellpadding="0" cellspacing="0"><tr>
        <td style="width:25%%;vertical-align:middle">
          <div style="color:#475569;font-size:0.6rem;text-transform:uppercase;
                       letter-spacing:0.08em;font-weight:600">Incidents</div>
          <div style="color:#f8fafc;font-size:1.4rem;font-weight:800;
                       line-height:1;margin-top:2px">{count}</div>
        </td>
        <td style="width:1px;background:#334155"></td>
        <td style="padding-left:20px;vertical-align:middle">
          <div style="color:#475569;font-size:0.6rem;text-transform:uppercase;
                       letter-spacing:0.08em;font-weight:600;margin-bottom:2px">Condition</div>
          <div style="color:#94a3b8;font-size:0.8rem;font-weight:500">{condition}</div>
        </td>
        <td style="text-align:right;vertical-align:middle;white-space:nowrap">
          <div style="color:#475569;font-size:0.6rem;text-transform:uppercase;
                       letter-spacing:0.08em;font-weight:600;margin-bottom:2px">Max Severity</div>
          <div style="color:#f8fafc;font-size:0.8rem;font-weight:700;
                       text-transform:uppercase">{max_sev}</div>
        </td>
      </tr></table>
    </td>
  </tr>

  <!-- BODY -->
  <tr>
    <td style="background:#ffffff;padding:24px 28px 8px">

      <div style="font-size:0.62rem;font-weight:700;text-transform:uppercase;
                   letter-spacing:0.1em;color:#94a3b8;margin-bottom:10px">By Severity</div>
      <table width="100%%" cellpadding="0" cellspacing="0" style="margin-bottom:24px">
        <tr>{sev_cells}</tr>
      </table>

      <div style="font-size:0.62rem;font-weight:700;text-transform:uppercase;
                   letter-spacing:0.1em;color:#94a3b8;margin-bottom:10px">
        Incident Details {trunc_note}
      </div>
      <table width="100%%" cellpadding="0" cellspacing="0"
             style="border-top:1px solid #e2e8f0">
        <thead>
          <tr>
            <th style="padding:7px 10px 7px 0;font-size:0.62rem;font-weight:700;
                        text-transform:uppercase;letter-spacing:0.07em;color:#94a3b8;
                        text-align:left;border-bottom:1px solid #e2e8f0">Type</th>
            <th style="padding:7px 10px;font-size:0.62rem;font-weight:700;
                        text-transform:uppercase;letter-spacing:0.07em;color:#94a3b8;
                        text-align:left;border-bottom:1px solid #e2e8f0">Entity</th>
            <th style="padding:7px 10px;font-size:0.62rem;font-weight:700;
                        text-transform:uppercase;letter-spacing:0.07em;color:#94a3b8;
                        text-align:left;border-bottom:1px solid #e2e8f0">Layers</th>
            <th style="padding:7px 0 7px 10px;font-size:0.62rem;font-weight:700;
                        text-transform:uppercase;letter-spacing:0.07em;color:#94a3b8;
                        text-align:right;border-bottom:1px solid #e2e8f0">Sev.</th>
          </tr>
        </thead>
        <tbody>{rows}</tbody>
      </table>
    </td>
  </tr>

  {test_row}

  <!-- CTA -->
  <tr>
    <td style="background:#ffffff;padding:20px 28px 24px;
               border-top:1px solid #f1f5f9;text-align:center">
      <a href="http://localhost:4200/incidents"
         style="display:inline-block;background:#0f172a;color:#f8fafc;
                text-decoration:none;font-weight:600;font-size:0.78rem;
                padding:11px 28px;border-radius:6px;letter-spacing:0.02em">
        Open CrossLayer Dashboard
      </a>
    </td>
  </tr>

  <!-- FOOTER -->
  <tr>
    <td style="background:#f8fafc;border:1px solid #e2e8f0;border-top:none;
               border-radius:0 0 8px 8px;padding:14px 28px">
      <div style="font-size:0.64rem;color:#94a3b8;line-height:1.7">
        CrossLayer Security Platform &middot; {ts_full} UTC<br>
        Rule: <em>{rule_name}</em> &middot; Condition: {condition}
        &middot; 5-minute repeat cooldown
      </div>
    </td>
  </tr>

</table>
</td></tr>
</table>
</body>
</html>""".format(
        test_pfx    = test_prefix,
        rule_name   = rule.name,
        count       = count,
        plural      = "s" if count != 1 else "",
        ts_short    = ts_short,
        ts_full     = ts_full,
        max_sev     = max_sev.upper(),
        label_tag   = "TEST ALERT" if is_test else "ALERT",
        alert_title = ("Test -- %s" % rule.name) if is_test
                      else ("Security Alert: %s" % rule.name),
        condition   = condition_label,
        sev_cells   = sev_cells_html,
        rows        = rows_html,
        trunc_note  = trunc_note,
        test_row    = test_row_html,
    )

    text_body = (
        "%sCrossLayer Security Alert\n"
        "%s\n\n"
        "Rule:      %s\n"
        "Condition: %s\n"
        "Severity:  %s\n"
        "Time:      %s UTC\n"
        "Incidents: %d\n\n"
        "Breakdown  Critical:%d  High:%d  Medium:%d  Low:%d\n\n"
        "Incidents:\n%s\n"
        "Dashboard: http://localhost:4200/incidents\n"
    ) % (
        test_prefix, "-" * 40,
        rule.name, condition_label, max_sev.upper(), ts_full, count,
        sev_counts_map["critical"], sev_counts_map["high"],
        sev_counts_map["medium"],   sev_counts_map["low"],
        plain_list,
    )

    cfg       = get_settings()
    from_addr = cfg.SMTP_FROM or cfg.SMTP_USER

    msg            = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = from_addr
    msg["To"]      = rule.notify_target
    msg.attach(MIMEText(text_body, "plain"))
    msg.attach(MIMEText(html_body, "html"))
    return msg

def _send_email_sync(rule, incidents, now):
    cfg = get_settings()
    if not cfg.SMTP_USER or not cfg.SMTP_PASS or cfg.SMTP_USER == "your_gmail@gmail.com":
        logger.warning("SMTP not configured -- skipping email for rule '%s'", rule.name)
        return
    msg = _build_email(rule, incidents, now, is_test=False)
    try:
        with smtplib.SMTP_SSL(cfg.SMTP_HOST, cfg.SMTP_PORT, timeout=10) as srv:
            srv.login(cfg.SMTP_USER, cfg.SMTP_PASS)
            srv.sendmail(cfg.SMTP_FROM or cfg.SMTP_USER, rule.notify_target, msg.as_string())
        logger.info(
            "Alert email sent -> %s | rule '%s' | %d incident(s)",
            rule.notify_target, rule.name, len(incidents),
        )
    except Exception as exc:
        logger.error("Alert email failed for rule '%s': %s", rule.name, exc)

def _send_webhook(url, payload):
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

def evaluate_and_fire(db, incidents):

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
        if rule.last_fired_at and (now - rule.last_fired_at) < cooldown:
            remaining = int((cooldown - (now - rule.last_fired_at)).total_seconds() / 60)
            logger.info(
                "Rule '%s' skipped -- cooldown active (%d min remaining)", rule.name, remaining
            )
            continue

        matching = [inc for inc in incidents if _rule_matches(rule, inc)]
        logger.info(
            "Rule '%s' (cond=%s layer=%r): %d/%d incidents matched",
            rule.name, rule.condition, rule.layer or "all", len(matching), len(incidents),
        )
        if not matching:
            continue

        if rule.notify_method == "email" and rule.notify_target:
            snap = list(matching)
            t = threading.Thread(
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
