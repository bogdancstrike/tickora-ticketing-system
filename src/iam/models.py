"""IAM ORM — User table is the bridge between Keycloak subjects and Tickora rows."""
import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.core.db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class User(Base):
    __tablename__ = "users"

    id:                Mapped[str]      = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    keycloak_subject:  Mapped[str]      = mapped_column(String(255), unique=True, nullable=False, index=True)
    username:          Mapped[str | None] = mapped_column(String(255), index=True)
    email:             Mapped[str | None] = mapped_column(String(255), index=True)
    first_name:        Mapped[str | None] = mapped_column(String(255))
    last_name:         Mapped[str | None] = mapped_column(String(255))
    user_type:         Mapped[str]      = mapped_column(String(50), nullable=False, default="internal")
    is_active:         Mapped[bool]     = mapped_column(Boolean, nullable=False, default=True)
    created_at:        Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at:        Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=lambda: datetime.now(timezone.utc), nullable=False)
