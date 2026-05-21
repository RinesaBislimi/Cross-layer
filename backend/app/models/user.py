"""User model for JWT authentication."""

from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Integer, String

from ..db import Base


class User(Base):
    __tablename__ = "users"

    id              = Column(Integer, primary_key=True, autoincrement=True)
    email           = Column(String(255), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    full_name       = Column(String(200), nullable=True, default="")
    role            = Column(String(50), nullable=False, default="analyst")
    # roles: admin | analyst | viewer
    is_active       = Column(Boolean, nullable=False, default=True)
    created_at      = Column(DateTime, nullable=False, default=datetime.utcnow)
    last_login      = Column(DateTime, nullable=True)
