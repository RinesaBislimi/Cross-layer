from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class IncidentSchema(BaseModel):
    id: int
    entity: Optional[str] = None
    type: str
    severity: Optional[str] = None
    start_time: datetime
    end_time: Optional[datetime] = None
    events: Optional[List[int]] = None
    attributes: Optional[Dict[str, Any]] = None

    class Config:
        from_attributes = True

