from datetime import datetime
from sqlalchemy import Column, DateTime, Index, Integer, String, Float, JSON, Text
from .base import Base

RAW_MAX_LENGTH = 10000

class LogEvent(Base):
    __tablename__ = "log_events"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, nullable=False, index=True)
    layer = Column(String(50), nullable=False, index=True)
    source = Column(String(50), nullable=False, index=True)
    entity = Column(String(100), index=True, nullable=True)
    label = Column(Integer, nullable=True, default=0, index=True)
    confidence = Column(Float, nullable=True)
    message = Column(Text, nullable=True)
    raw = Column(Text, nullable=True)
    features = Column(JSON, nullable=True)
    metadata_json = Column(JSON, nullable=True)

    __table_args__ = (
        Index("ix_log_events_source_label", "source", "label"),
        Index("ix_log_events_source_ts",    "source", "timestamp"),
        Index("ix_log_events_layer_ts",     "layer",  "timestamp"),
    )

    def __repr__(self):
        return f"<LogEvent(id={self.id}, layer={self.layer}, entity={self.entity}, label={self.label})>"