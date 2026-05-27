
import logging
from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db import get_db
from ..models.alert_rule import AlertRule
from ..models.incidents import Incident

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/alert-rules", tags=["alert-rules"])

class AlertRuleCreate(BaseModel):
    name:          str
    condition:     str
    layer:         str  = ""
    notify_method: str  = "browser"
    notify_target: str  = ""

class AlertRuleOut(BaseModel):
    id:            int
    name:          str
    condition:     str
    layer:         str
    notify_method: str
    notify_target: str
    enabled:       bool
    created_at:    str
    trigger_count: int
    last_fired_at: Optional[str]

    class Config:
        from_attributes = True

def _to_out(r):
    return {
        "id":            r.id,
        "name":          r.name,
        "condition":     r.condition,
        "layer":         r.layer or "",
        "notify_method": r.notify_method,
        "notify_target": r.notify_target or "",
        "enabled":       r.enabled,
        "created_at":    r.created_at.isoformat() if r.created_at else "",
        "trigger_count": r.trigger_count or 0,
        "last_fired_at": r.last_fired_at.isoformat() if r.last_fired_at else None,
    }

@router.get("/")
def list_rules(db: Session = Depends(get_db)):
    rules = db.query(AlertRule).order_by(AlertRule.id.desc()).all()
    return [_to_out(r) for r in rules]

@router.post("/", status_code=201)
def create_rule(payload: AlertRuleCreate, db: Session = Depends(get_db)):
    if not payload.name.strip():
        raise HTTPException(status_code=422, detail="Rule name is required.")
    valid_conditions = {
        "any_anomaly", "critical_severity", "high_severity", "cross_layer", "entity_repeat"
    }
    if payload.condition not in valid_conditions:
        raise HTTPException(status_code=422, detail="Invalid condition value.")
    valid_methods = {"browser", "webhook", "email"}
    if payload.notify_method not in valid_methods:
        raise HTTPException(status_code=422, detail="Invalid notify_method.")
    if payload.notify_method in ("webhook", "email") and not payload.notify_target.strip():
        raise HTTPException(
            status_code=422,
            detail="notify_target is required for webhook and email methods.",
        )

    rule = AlertRule(
        name          = payload.name.strip(),
        condition     = payload.condition,
        layer         = payload.layer or "",
        notify_method = payload.notify_method,
        notify_target = payload.notify_target.strip(),
        enabled       = True,
        created_at    = datetime.utcnow(),
        trigger_count = 0,
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)
    logger.info("Alert rule created: id=%s name=%r", rule.id, rule.name)
    return _to_out(rule)

@router.delete("/{rule_id}", status_code=204)
def delete_rule(rule_id: int, db: Session = Depends(get_db)):
    rule = db.query(AlertRule).filter(AlertRule.id == rule_id).first()
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found.")
    db.delete(rule)
    db.commit()

@router.patch("/{rule_id}/toggle")
def toggle_rule(rule_id: int, db: Session = Depends(get_db)):
    rule = db.query(AlertRule).filter(AlertRule.id == rule_id).first()
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found.")
    rule.enabled = not rule.enabled
    db.commit()
    db.refresh(rule)
    return _to_out(rule)

@router.post("/trigger")
def trigger_now(limit: int = 100, db: Session = Depends(get_db)):
    from ..services.alert_service import _rule_matches, _send_email_sync
    import threading

    rules = db.query(AlertRule).filter(AlertRule.enabled.is_(True)).all()
    incidents = (
        db.query(Incident)
        .order_by(Incident.id.desc())
        .limit(limit)
        .all()
    )

    report = {
        "rules_enabled":    len(rules),
        "incidents_tested": len(incidents),
        "results": [],
    }

    now = datetime.utcnow()

    for rule in rules:
        matching = [inc for inc in incidents if _rule_matches(rule, inc)]
        entry = {
            "rule_id":       rule.id,
            "rule_name":     rule.name,
            "condition":     rule.condition,
            "layer_filter":  rule.layer or "(all)",
            "notify_method": rule.notify_method,
            "notify_target": rule.notify_target,
            "matched":       len(matching),
            "fired":         False,
            "detail":        "",
        }

        if not matching:
            entry["detail"] = "No incidents matched the condition."
        elif rule.notify_method == "email":
            if not rule.notify_target:
                entry["detail"] = "No email address configured."
            else:
                snap = list(matching)
                t = threading.Thread(
                    target=_send_email_sync, args=(rule, snap, now), daemon=True
                )
                t.start()
                rule.trigger_count = (rule.trigger_count or 0) + len(matching)
                rule.last_fired_at = now
                entry["fired"]  = True
                entry["detail"] = "Email queued to %s (%d incidents)" % (
                    rule.notify_target, len(matching)
                )
        elif rule.notify_method == "browser":
            entry["detail"] = "Browser notifications fire client-side only — use Test now button."
        elif rule.notify_method == "webhook":
            entry["detail"] = "Webhook: %s (%d incidents)" % (rule.notify_target, len(matching))
            entry["fired"]  = True

        report["results"].append(entry)

    try:
        db.commit()
    except Exception as exc:
        logger.warning("trigger_now commit failed: %s", exc)

    return report

@router.get("/debug")
def debug_rules(db: Session = Depends(get_db)):
    from ..services.alert_service import _rule_matches

    rules     = db.query(AlertRule).all()
    incidents = db.query(Incident).order_by(Incident.id.desc()).limit(20).all()

    sample_incidents = []
    for inc in incidents:
        attrs  = inc.attributes or {}
        layers = attrs.get("layers", []) if isinstance(attrs, dict) else []
        sample_incidents.append({
            "id":       inc.id,
            "type":     inc.type,
            "severity": inc.severity,
            "entity":   inc.entity,
            "layers":   layers,
        })

    rule_debug = []
    for rule in rules:
        matches = [inc.id for inc in incidents if _rule_matches(rule, inc)]
        rule_debug.append({
            **_to_out(rule),
            "sample_matches": matches,
        })

    return {
        "total_rules":     len(rules),
        "total_incidents": db.query(Incident).count(),
        "rules":           rule_debug,
        "sample_incidents": sample_incidents,
    }
