
from __future__ import annotations

import json
import logging
import threading
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from typing import List

from sqlalchemy.orm import Session

from ..models.incidents import Incident
from ..models.response_rule import ResponseRule

logger = logging.getLogger(__name__)

_COOLDOWN_MINUTES = 5

def _rule_matches(rule: ResponseRule, incident: Incident) -> bool:
    attrs  = incident.attributes or {}
    layers = attrs.get("layers", []) if isinstance(attrs, dict) else []
    sev    = (incident.severity or "").lower()
    itype  = (incident.type or "").lower()

    cond = rule.condition
    if cond == "any_anomaly":
        matched = True
    elif cond == "critical_severity":
        matched = sev == "critical"
    elif cond == "high_severity":
        matched = sev in ("high", "critical")
    elif cond == "cross_layer":
        matched = len(layers) > 1 or "cross" in itype
    elif cond == "entity_repeat":
        matched = bool(incident.entity)
    else:
        matched = False

    if not matched:
        return False

    layer_filter = (rule.layer or "").strip().lower()
    if layer_filter and layer_filter != "all":
        matched = any(layer_filter in str(l).lower() for l in layers)\
                  or layer_filter == (incident.entity or "").lower()

    return matched

def _fire_webhook(url: str, payload: dict) -> None:
    try:
        data = json.dumps(payload).encode()
        req  = urllib.request.Request(url, data=data,
                                      headers={"Content-Type": "application/json"},
                                      method="POST")
        with urllib.request.urlopen(req, timeout=10):
            pass
    except Exception as exc:
        logger.warning("Response rule webhook failed: %s", exc)

def evaluate_and_respond(db: Session, incidents: List[Incident]) -> int:
    if not incidents:
        return 0

    try:
        rules = db.query(ResponseRule).filter(ResponseRule.enabled.is_(True)).all()
    except Exception as exc:
        logger.warning("Failed to load response rules: %s", exc)
        return 0

    if not rules:
        return 0

    now   = datetime.utcnow()
    fired = 0

    for rule in rules:
        if rule.last_fired_at:
            if (now - rule.last_fired_at) < timedelta(minutes=_COOLDOWN_MINUTES):
                continue

        matching = [inc for inc in incidents if _rule_matches(rule, inc)]
        if not matching:
            continue

        fired += 1
        rule.trigger_count = (rule.trigger_count or 0) + 1
        rule.last_fired_at = now

        action = rule.action_type

        if action == "webhook" and rule.action_target:
            try:
                template = json.loads(rule.action_payload or "{}")
            except Exception:
                template = {}
            payload = {
                **template,
                "rule": rule.name,
                "condition": rule.condition,
                "incidents_matched": len(matching),
                "entities": list({i.entity for i in matching if i.entity}),
                "timestamp": now.isoformat(),
            }
            t = threading.Thread(target=_fire_webhook,
                                 args=(rule.action_target, payload), daemon=True)
            t.start()
            logger.info("Response rule '%s' fired webhook → %s (%d incidents)",
                        rule.name, rule.action_target, len(matching))

        elif action in ("block_ip", "isolate_host"):
            entities = [i.entity for i in matching if i.entity]
            logger.warning(
                "RESPONSE ACTION: %s — entities=%s (rule=%s, %d incidents)",
                action.upper(), entities, rule.name, len(matching),
            )

        elif action == "email_team" and rule.action_target:
            try:
                from .alert_service import _send_email_sync
                from ..models.alert_rule import AlertRule

                class _Proxy:
                    pass
                proxy = _Proxy()
                proxy.name          = rule.name
                proxy.condition     = rule.condition
                proxy.notify_target = rule.action_target
                proxy.notify_method = "email"

                t = threading.Thread(
                    target=_send_email_sync, args=(proxy, matching, now), daemon=True
                )
                t.start()
            except Exception as exc:
                logger.warning("Response rule email failed: %s", exc)

        elif action == "create_ticket":
            logger.info(
                "TICKET: %s — %d incidents matched (rule=%s)",
                rule.name, len(matching), rule.id
            )

    try:
        db.commit()
    except Exception as exc:
        logger.warning("response_service commit failed: %s", exc)

    return fired
