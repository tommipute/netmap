"""Fase 4: endpoint visti nelle tabelle MAC degli switch ("dov'è collegato questo PC?")."""
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.dcim import Interface


class Endpoint(Base):
    """Un MAC address e la porta di accesso dove è stato visto l'ultima volta.

    Lo aggiorna la scansione (tabelle MAC e ARP degli switch), non si modifica a mano.
    """

    __tablename__ = "endpoints"

    id: Mapped[int] = mapped_column(primary_key=True)
    mac: Mapped[str] = mapped_column(String(17), unique=True)
    ip: Mapped[str | None] = mapped_column(String(45), index=True)   # dall'ARP di router e switch L3
    interface_id: Mapped[int | None] = mapped_column(ForeignKey("interfaces.id", ondelete="SET NULL"), index=True)
    vlan: Mapped[int | None] = mapped_column(Integer)
    macs_on_port: Mapped[int | None] = mapped_column(Integer)  # >1: dietro la porta c'è altro (switchino, telefono)
    # Porta precedente: se il device si è spostato si vede da dove viene
    previous_interface_id: Mapped[int | None] = mapped_column(ForeignKey("interfaces.id", ondelete="SET NULL"))
    moved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    ip_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    interface: Mapped[Interface | None] = relationship(foreign_keys=[interface_id], lazy="joined")
    previous_interface: Mapped[Interface | None] = relationship(foreign_keys=[previous_interface_id], lazy="joined")
