from datetime import datetime
from sqlalchemy import Column, DateTime, Integer, String, JSON
from .base import Base

class Incident(Base):
    __tablename__ = "incidents"

    id = Column(Integer, primary_key=True, index=True)

    # IP / user / host / main entity
    entity = Column(String(100), index=True, nullable=True)

    # short description of incident
    type = Column(String(100), index=True, nullable=False)

    severity = Column(String(50), index=True, nullable=True)

    start_time = Column(DateTime, index=True, nullable=False, default=datetime.utcnow)
    end_time = Column(DateTime, index=True, nullable=True)

    # related LogEvent ids
    events = Column(JSON, nullable=True)

    # metadata / cross-layer features
    attributes = Column(JSON, nullable=True)
    
    def __repr__(self):
        return f"<Incident(id={self.id}, entity={self.entity}, type={self.type}, severity={self.severity})>"