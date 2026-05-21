"""Automated response / playbook rules."""

from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text

from ..db import Base


class ResponseRule(Base):
    __tablename__ = "response_rules"

    id            = Column(Integer, primary_key=True, autoincrement=True)
    name          = Column(String(200), nullable=False)
    description   = Column(Text, nullable=True, default="")

    # Trigger criteria (same as alert rules)
    condition     = Column(String(50), nullable=False)
    # any_anomaly | critical_severity | high_severity | cross_layer | entity_repeat
    layer         = Column(String(50), nullable=True, default="")

    # Action to perform when triggered
    action_type   = Column(String(50), nullable=False)
    # block_ip | isolate_host | webhook | create_ticket | email_team

    action_target = Column(String(500), nullable=True, default="")
    # webhook URL, email address, etc.

    action_payload = Column(Text, nullable=True, default="{}")
    # JSON template for webhook payload

    enabled       = Column(Boolean, nullable=False, default=True)
    created_at    = Column(DateTime, nullable=False, default=datetime.utcnow)
    trigger_count = Column(Integer, nullable=False, default=0)
    last_fired_at = Column(DateTime, nullable=True)
