from datetime import datetime
from typing import Any, Dict, Optional

from pydantic import BaseModel

class LogEventSchema(BaseModel):
    id: int
    layer: str
    source: str
    timestamp: datetime
    entity: Optional[str] = None
    raw: Optional[str] = None
    message: Optional[str] = None
    features: Optional[Dict[str, Any]] = None
    label: Optional[int] = None
    confidence: Optional[float] = None

    class Config:
        from_attributes = True

