from datetime import datetime
from sqlalchemy import Boolean, Column, DateTime, Integer, String
from .base import Base

class AlertRule(Base):
    __tablename__ = "alert_rules"

    id             = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name           = Column(String(200), nullable=False)
    condition      = Column(String(50),  nullable=False)
    layer          = Column(String(50),  nullable=True,  default="")
    notify_method  = Column(String(20),  nullable=False, default="browser")
    notify_target  = Column(String(500), nullable=True,  default="")
    enabled        = Column(Boolean,     nullable=False, default=True)
    created_at     = Column(DateTime,    nullable=False, default=datetime.utcnow)
    trigger_count  = Column(Integer,     nullable=False, default=0)
    last_fired_at  = Column(DateTime,    nullable=True)

    def __repr__(self):
        return f"<AlertRule(id={self.id}, name={self.name!r}, condition={self.condition}, enabled={self.enabled})>"
