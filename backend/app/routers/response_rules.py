"""CRUD REST endpoints for automated response / playbook rules."""

import logging
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db import get_db
from ..models.response_rule import ResponseRule

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/response-rules", tags=["response-rules"])


# ── Pydantic schemas ──────────────────────────────────────────────────────────

class ResponseRuleCreate(BaseModel):
    name:           str
    description:    str  = ""
    condition:      str
    layer:          str  = ""
    action_type:    str
    action_target:  str  = ""
    action_payload: str  = "{}"


class ResponseRuleOut(BaseModel):
    id:             int
    name:           str
    description:    str
    condition:      str
    layer:          str
    action_type:    str
    action_target:  str
    action_payload: str
    enabled:        bool
    created_at:     str
    trigger_count:  int
    last_fired_at:  Optional[str]

    class Config:
        from_attributes = True


VALID_CONDITIONS = {
    "any_anomaly", "critical_severity", "high_severity", "cross_layer", "entity_repeat"
}
VALID_ACTIONS = {
    "block_ip", "isolate_host", "webhook", "create_ticket", "email_team"
}


def _to_out(r: ResponseRule) -> dict:
    return {
        "id":             r.id,
        "name":           r.name,
        "description":    r.description or "",
        "condition":      r.condition,
        "layer":          r.layer or "",
        "action_type":    r.action_type,
        "action_target":  r.action_target or "",
        "action_payload": r.action_payload or "{}",
        "enabled":        r.enabled,
        "created_at":     r.created_at.isoformat() if r.created_at else "",
        "trigger_count":  r.trigger_count or 0,
        "last_fired_at":  r.last_fired_at.isoformat() if r.last_fired_at else None,
    }


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/")
def list_rules(db: Session = Depends(get_db)):
    rules = db.query(ResponseRule).order_by(ResponseRule.id.desc()).all()
    return [_to_out(r) for r in rules]


@router.post("/", status_code=201)
def create_rule(payload: ResponseRuleCreate, db: Session = Depends(get_db)):
    if not payload.name.strip():
        raise HTTPException(status_code=422, detail="Rule name is required.")
    if payload.condition not in VALID_CONDITIONS:
        raise HTTPException(status_code=422, detail="Invalid condition.")
    if payload.action_type not in VALID_ACTIONS:
        raise HTTPException(status_code=422, detail=f"Invalid action_type. Must be one of: {', '.join(VALID_ACTIONS)}")
    if payload.action_type in ("webhook", "email_team") and not payload.action_target.strip():
        raise HTTPException(status_code=422, detail="action_target is required for webhook and email_team actions.")

    # Validate JSON payload
    import json
    try:
        json.loads(payload.action_payload or "{}")
    except Exception:
        raise HTTPException(status_code=422, detail="action_payload must be valid JSON.")

    rule = ResponseRule(
        name           = payload.name.strip(),
        description    = payload.description.strip(),
        condition      = payload.condition,
        layer          = payload.layer or "",
        action_type    = payload.action_type,
        action_target  = payload.action_target.strip(),
        action_payload = payload.action_payload or "{}",
        enabled        = True,
        created_at     = datetime.utcnow(),
        trigger_count  = 0,
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)
    logger.info("Response rule created: id=%s name=%r action=%s", rule.id, rule.name, rule.action_type)
    return _to_out(rule)


@router.delete("/{rule_id}", status_code=204)
def delete_rule(rule_id: int, db: Session = Depends(get_db)):
    rule = db.query(ResponseRule).filter(ResponseRule.id == rule_id).first()
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found.")
    db.delete(rule)
    db.commit()


@router.patch("/{rule_id}/toggle")
def toggle_rule(rule_id: int, db: Session = Depends(get_db)):
    rule = db.query(ResponseRule).filter(ResponseRule.id == rule_id).first()
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found.")
    rule.enabled = not rule.enabled
    db.commit()
    db.refresh(rule)
    return _to_out(rule)


@router.post("/test/{rule_id}")
def test_rule(rule_id: int, limit: int = 50, db: Session = Depends(get_db)):
    """Test a response rule against recent incidents (dry run — does NOT fire actions)."""
    from ..models.incidents import Incident
    from ..services.response_service import _rule_matches

    rule = db.query(ResponseRule).filter(ResponseRule.id == rule_id).first()
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found.")

    incidents = db.query(Incident).order_by(Incident.id.desc()).limit(limit).all()
    matching  = [inc.id for inc in incidents if _rule_matches(rule, inc)]

    return {
        "rule_id":        rule_id,
        "rule_name":      rule.name,
        "incidents_tested": len(incidents),
        "matched":        len(matching),
        "matched_ids":    matching[:20],
        "action_type":    rule.action_type,
        "action_target":  rule.action_target,
        "dry_run":        True,
    }
