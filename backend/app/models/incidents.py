from datetime import datetime
from sqlalchemy import Column, DateTime, Integer, String, JSON
from .base import Base

class Incident(Base):
    __tablename__ = "incidents"

    id = Column(Integer, primary_key=True, index=True)

    entity = Column(String(100), index=True, nullable=True)

    type = Column(String(100), index=True, nullable=False)

    severity = Column(String(50), index=True, nullable=True)

    start_time = Column(DateTime, index=True, nullable=False, default=datetime.utcnow)
    end_time = Column(DateTime, index=True, nullable=True)

    events = Column(JSON, nullable=True)

    attributes = Column(JSON, nullable=True)
    def __repr__(self):
        return f"<Incident(id={self.id}, entity={self.entity}, type={self.type}, severity={self.severity})>"