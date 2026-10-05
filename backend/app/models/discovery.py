"""Scansione SNMP: profili di accesso, job, esecuzioni e modifiche proposte da approvare."""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, false, func, true
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, JSONType, TimestampMixin
from app.models.enums import ChangeStatus, RunStatus, SnmpVersion


class SnmpProfile(TimestampMixin, Base):
    """Credenziali SNMP. I segreti sono cifrati (Fernet) e non tornano mai nelle risposte dell'API."""

    __tablename__ = "snmp_profiles"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    version: Mapped[str] = mapped_column(String(5), default=SnmpVersion.V2C.value, server_default=SnmpVersion.V2C.value)
    port: Mapped[int] = mapped_column(Integer, default=161, server_default="161")
    timeout: Mapped[float] = mapped_column(Float, default=2.0, server_default="2")
    retries: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    community_enc: Mapped[str | None] = mapped_column(Text)
    # SNMPv3
    username: Mapped[str | None] = mapped_column(String(100))
    auth_protocol: Mapped[str | None] = mapped_column(String(10))
    auth_key_enc: Mapped[str | None] = mapped_column(Text)
    priv_protocol: Mapped[str | None] = mapped_column(String(10))
    priv_key_enc: Mapped[str | None] = mapped_column(Text)
    context_name: Mapped[str | None] = mapped_column(String(100))  # SNMPv3, quasi sempre vuoto
    description: Mapped[str | None] = mapped_column(Text)

    @property
    def has_community(self) -> bool:
        return bool(self.community_enc)

    @property
    def has_auth_key(self) -> bool:
        return bool(self.auth_key_enc)

    @property
    def has_priv_key(self) -> bool:
        return bool(self.priv_key_enc)


class DiscoveryJob(TimestampMixin, Base):
    """Cosa scansionare, con quali profili, ogni quanto e cosa applicare senza chiedere."""

    __tablename__ = "discovery_jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    # ["10.0.0.0/24", "10.0.1.5", "10.0.2.1-10.0.2.20"]
    targets: Mapped[list] = mapped_column(JSONType, default=list)
    # Profili SNMP provati in quest'ordine: vince il primo che risponde
    profile_ids: Mapped[list] = mapped_column(JSONType, default=list)
    # Sede in cui finiscono i device nuovi
    site_id: Mapped[int] = mapped_column(ForeignKey("sites.id", ondelete="RESTRICT"), index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    interval_hours: Mapped[int | None] = mapped_column(Integer)  # vuoto = solo a mano
    auto_new_interfaces: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    auto_new_ips: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    description: Mapped[str | None] = mapped_column(Text)


class DiscoveryRun(Base):
    __tablename__ = "discovery_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("discovery_jobs.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(
        String(20), default=RunStatus.QUEUED.value, server_default=RunStatus.QUEUED.value, index=True
    )
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    hosts_total: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    hosts_responded: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    changes_proposed: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    changes_applied: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    log: Mapped[str] = mapped_column(Text, default="", server_default="")


class DiscoveryChange(Base):
    """Modifica proposta da una scansione.

    `key` identifica oggetto e azione: se una scansione successiva rivede la stessa modifica
    aggiorna la riga in attesa invece di crearne un'altra.
    """

    __tablename__ = "discovery_changes"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("discovery_runs.id", ondelete="CASCADE"), index=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("discovery_jobs.id", ondelete="CASCADE"), index=True)
    host: Mapped[str] = mapped_column(String(45))  # IP scansionato che l'ha generata
    device_id: Mapped[int | None] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"), index=True)
    device_label: Mapped[str] = mapped_column(String(255))  # per raggruppare, anche i device nuovi
    object_type: Mapped[str] = mapped_column(String(20))
    action: Mapped[str] = mapped_column(String(10))
    object_id: Mapped[int | None] = mapped_column(Integer)
    key: Mapped[str] = mapped_column(String(255), index=True)
    summary: Mapped[str] = mapped_column(String(500))
    data: Mapped[dict] = mapped_column(JSONType, default=dict)  # cosa applicare, con gli id
    diff: Mapped[list] = mapped_column(JSONType, default=list)  # [[campo, attuale, proposto], ...] da mostrare
    status: Mapped[str] = mapped_column(
        String(20), default=ChangeStatus.PENDING.value, server_default=ChangeStatus.PENDING.value, index=True
    )
    auto: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())  # applicata senza approvazione
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
