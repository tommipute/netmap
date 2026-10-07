"""Storico delle modifiche: chi ha cambiato cosa e quando (lo scrive services/audit.py, mai a mano)."""
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, JSONType


class AuditEntry(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    username: Mapped[str | None] = mapped_column(String(100))  # resta anche se l'utente viene eliminato
    source: Mapped[str] = mapped_column(String(20))  # utente / scansione / import / sistema
    object_type: Mapped[str] = mapped_column(String(30), index=True)
    object_id: Mapped[int] = mapped_column(Integer, index=True)
    label: Mapped[str] = mapped_column(String(255))  # nome leggibile al momento della modifica
    action: Mapped[str] = mapped_column(String(10))  # create / update / delete
    changes: Mapped[list] = mapped_column(JSONType, default=list)  # [[campo, prima, dopo], ...]
    # Device coinvolti (due per un cavo): per lo storico nella scheda del device, anche dopo l'eliminazione
    device_id: Mapped[int | None] = mapped_column(Integer, index=True)
    device_id_2: Mapped[int | None] = mapped_column(Integer, index=True)
