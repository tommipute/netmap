"""Fase 4: endpoint visti nelle tabelle MAC degli switch ("dov'è collegato questo PC?") e storico delle porte."""
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Integer, String, func
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


class PortStat(Base):
    """Storico di una porta per intervallo: 5 minuti (2 giorni), ora (30 giorni), giorno (un anno).

    Somme, non medie: un campione nuovo nello stesso intervallo si aggiunge (services/port_stats.py).
    """

    __tablename__ = "port_stats"
    __table_args__ = (Index("ix_port_stats_period_at", "period", "at"),)

    interface_id: Mapped[int] = mapped_column(ForeignKey("interfaces.id", ondelete="CASCADE"), primary_key=True)
    period: Mapped[str] = mapped_column(String(2), primary_key=True)     # 5m, 1h, 1d
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)  # inizio dell'intervallo
    seconds: Mapped[int] = mapped_column(Integer, default=0)             # secondi coperti dai campioni
    in_octets: Mapped[int | None] = mapped_column(BigInteger)            # byte (NULL = lo switch non li dà)
    out_octets: Mapped[int | None] = mapped_column(BigInteger)
    in_peak_bps: Mapped[int | None] = mapped_column(BigInteger)          # il campione da 5 minuti più alto
    out_peak_bps: Mapped[int | None] = mapped_column(BigInteger)
    errors: Mapped[int] = mapped_column(BigInteger, default=0)           # errori in + out
    discards: Mapped[int] = mapped_column(BigInteger, default=0)         # scarti in + out
    up_seconds: Mapped[int] = mapped_column(Integer, default=0)
    poe_mws: Mapped[int | None] = mapped_column(BigInteger)              # mW × secondi: media = poe_mws / seconds
