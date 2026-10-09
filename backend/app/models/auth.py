"""Fase 4: utenti e ruoli per il login; accesso con Active Directory."""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text, false, true
from sqlalchemy.orm import Mapped, mapped_column, validates

from app.models.base import Base, TimestampMixin
from app.models.enums import DirectorySecurity, UserRole, UserSource


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(100), unique=True)
    first_name: Mapped[str | None] = mapped_column(String(100))
    last_name: Mapped[str | None] = mapped_column(String(100))
    # "Nome Cognome", ricavato dai due campi: per menu utente, stampe, ricerca
    full_name: Mapped[str | None] = mapped_column(String(200))
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), default=UserRole.VIEWER.value, server_default=UserRole.VIEWER.value)
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    # Cambia a ogni cambio password: i token emessi prima smettono di valere
    token_version: Mapped[int] = mapped_column(default=0, server_default="0")
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # local = password in NetMap; ad = utente di dominio: password e ruolo vengono da Active Directory a ogni accesso
    source: Mapped[str] = mapped_column(String(20), default=UserSource.LOCAL.value, server_default=UserSource.LOCAL.value)

    @validates("first_name", "last_name")
    def _names(self, key: str, value: str | None) -> str | None:
        value = (value or "").strip() or None
        names = {"first_name": self.first_name, "last_name": self.last_name, key: value}
        self.full_name = " ".join(n for n in (names["first_name"], names["last_name"]) if n) or None
        return value


class DirectorySettings(TimestampMixin, Base):
    """Accesso con Active Directory (una riga sola). Niente account di servizio: si entra con utente@dominio."""

    __tablename__ = "directory_settings"

    id: Mapped[int] = mapped_column(primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    servers: Mapped[str] = mapped_column(String(500), default="", server_default="")  # domain controller, in ordine
    security: Mapped[str] = mapped_column(String(10), default=DirectorySecurity.LDAPS.value,
                                          server_default=DirectorySecurity.LDAPS.value)
    port: Mapped[int | None] = mapped_column(Integer)  # vuota = 636 con LDAPS, 389 altrimenti
    verify_cert: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    ca_cert: Mapped[str | None] = mapped_column(Text)  # certificato della CA del dominio (PEM)
    domain: Mapped[str] = mapped_column(String(255), default="", server_default="")  # dominio DNS, es. azienda.local
    base_dn: Mapped[str | None] = mapped_column(String(500))  # vuoto = dal dominio (DC=azienda,DC=local)
    admin_group: Mapped[str | None] = mapped_column(String(500))
    editor_group: Mapped[str | None] = mapped_column(String(500))
    viewer_group: Mapped[str | None] = mapped_column(String(500))
    default_role: Mapped[str | None] = mapped_column(String(20))  # chi non è in nessun gruppo: vuoto = non entra
