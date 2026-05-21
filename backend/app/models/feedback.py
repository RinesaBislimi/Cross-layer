"""Analyst feedback on incidents — used to refine ML models."""

from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text

from ..db import Base


class IncidentFeedback(Base):
    __tablename__ = "incident_feedback"

    id          = Column(Integer, primary_key=True, autoincrement=True)
    incident_id = Column(Integer, ForeignKey("incidents.id", ondelete="CASCADE"),
                         nullable=False, index=True)
    analyst_id  = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"),
                         nullable=True)
    verdict     = Column(String(30), nullable=False)
    # verdict: true_positive | false_positive | needs_review
    notes       = Column(Text, nullable=True, default="")
    created_at  = Column(DateTime, nullable=False, default=datetime.utcnow)
