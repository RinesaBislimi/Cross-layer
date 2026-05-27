
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text

from ..db import Base

class ResponseRule(Base):
    __tablename__ = "response_rules"

    id            = Column(Integer, primary_key=True, autoincrement=True)
    name          = Column(String(200), nullable=False)
    description   = Column(Text, nullable=True, default="")

    condition     = Column(String(50), nullable=False)
    layer         = Column(String(50), nullable=True, default="")

    action_type   = Column(String(50), nullable=False)

    action_target = Column(String(500), nullable=True, default="")

    action_payload = Column(Text, nullable=True, default="{}")

    enabled       = Column(Boolean, nullable=False, default=True)
    created_at    = Column(DateTime, nullable=False, default=datetime.utcnow)
    trigger_count = Column(Integer, nullable=False, default=0)
    last_fired_at = Column(DateTime, nullable=True)
