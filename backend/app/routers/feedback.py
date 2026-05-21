"""Analyst feedback on incidents — mark as true/false positive, notes."""

import logging
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db import get_db
from ..models.feedback import IncidentFeedback
from ..models.incidents import Incident
from ..routers.auth import get_current_user
from ..models.user import User

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/incidents", tags=["feedback"])


class FeedbackIn(BaseModel):
    verdict: str       # true_positive | false_positive | needs_review
    notes:   str = ""


class FeedbackOut(BaseModel):
    id:          int
    incident_id: int
    analyst_id:  Optional[int]
    verdict:     str
    notes:       str
    created_at:  str

    class Config:
        from_attributes = True


def _to_out(f: IncidentFeedback) -> dict:
    return {
        "id":          f.id,
        "incident_id": f.incident_id,
        "analyst_id":  f.analyst_id,
        "verdict":     f.verdict,
        "notes":       f.notes or "",
        "created_at":  f.created_at.isoformat() if f.created_at else "",
    }


VALID_VERDICTS = {"true_positive", "false_positive", "needs_review"}


@router.post("/{incident_id}/feedback", status_code=201)
def submit_feedback(
    incident_id: int,
    payload: FeedbackIn,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Submit analyst feedback for an incident."""
    if not db.query(Incident).filter(Incident.id == incident_id).first():
        raise HTTPException(status_code=404, detail="Incident not found.")
    if payload.verdict not in VALID_VERDICTS:
        raise HTTPException(
            status_code=422,
            detail=f"verdict must be one of: {', '.join(VALID_VERDICTS)}"
        )

    # Upsert: one feedback entry per analyst per incident
    existing = db.query(IncidentFeedback).filter(
        IncidentFeedback.incident_id == incident_id,
        IncidentFeedback.analyst_id  == current_user.id,
    ).first()

    if existing:
        existing.verdict    = payload.verdict
        existing.notes      = payload.notes.strip()
        existing.created_at = datetime.utcnow()
        db.commit()
        db.refresh(existing)
        return _to_out(existing)
    else:
        fb = IncidentFeedback(
            incident_id = incident_id,
            analyst_id  = current_user.id,
            verdict     = payload.verdict,
            notes       = payload.notes.strip(),
            created_at  = datetime.utcnow(),
        )
        db.add(fb)
        db.commit()
        db.refresh(fb)
        logger.info("Feedback %s on incident %d by user %d", payload.verdict, incident_id, current_user.id)
        return _to_out(fb)


@router.get("/{incident_id}/feedback")
def get_feedback(
    incident_id: int,
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get all feedback for an incident."""
    entries = db.query(IncidentFeedback).filter(
        IncidentFeedback.incident_id == incident_id
    ).order_by(IncidentFeedback.created_at.desc()).all()
    return [_to_out(f) for f in entries]


@router.get("/feedback/summary")
def feedback_summary(
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Aggregated feedback counts by verdict — used for model retraining stats."""
    from sqlalchemy import func
    rows = db.query(
        IncidentFeedback.verdict,
        func.count(IncidentFeedback.id).label("count")
    ).group_by(IncidentFeedback.verdict).all()

    total = sum(r.count for r in rows)
    return {
        "total": total,
        "by_verdict": {r.verdict: r.count for r in rows},
    }
