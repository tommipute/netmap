"""Fase 4: utenti e ruoli per il login."""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, true
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin
from app.models.enums import UserRole


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(100), unique=True)
    full_name: Mapped[str | None] = mapped_column(String(200))
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), default=UserRole.VIEWER.value, server_default=UserRole.VIEWER.value)
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    # Cambia a ogni cambio password: i token emessi prima smettono di valere
    token_version: Mapped[int] = mapped_column(default=0, server_default="0")
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
