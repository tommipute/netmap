"""Import da NetBox e dalle altre sorgenti: una riga per ogni import (o simulazione) chiesto dall'interfaccia,
eseguito dal worker."""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, false, func, text, true
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, JSONType
from app.models.enums import RunStatus


class ImportRun(Base):
    __tablename__ = "import_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(20), default="netbox", server_default="netbox")
    url: Mapped[str] = mapped_column(String(500))
    # Segreti ({"token", "app_token"}) cifrati con la chiave dei segreti: servono solo al worker, cancellati a fine import
    token_enc: Mapped[str | None] = mapped_column(Text)
    username: Mapped[str | None] = mapped_column(String(255))  # PRTG, Observium, GLPI, Zabbix con utente e password
    # Sede per i device che nella sorgente non ne hanno una (Zabbix, PRTG senza sonda…)
    default_site: Mapped[str | None] = mapped_column(String(100))
    verify_tls: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    # Sedi di NetBox, gruppi di Zabbix, posizioni di LibreNMS… da importare (vuoto = tutto)
    site_ids: Mapped[list] = mapped_column(JSONType, default=list, server_default=text("'[]'"))
    site_names: Mapped[list] = mapped_column(JSONType, default=list, server_default=text("'[]'"))
    dry_run: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    status: Mapped[str] = mapped_column(
        String(20), default=RunStatus.QUEUED.value, server_default=RunStatus.QUEUED.value, index=True
    )
    # {"device": {"created": 3, "existing": 1, "failed": 0, "skipped": 0}, ...}
    counts: Mapped[dict] = mapped_column(JSONType, default=dict, server_default=text("'{}'"))
    # Oggetti non importati e avvisi: [{"kind": "device", "name": "sw-01", "message": "..."}]
    problems: Mapped[list] = mapped_column(JSONType, default=list, server_default=text("'[]'"))
    source_version: Mapped[str | None] = mapped_column(String(50))
    log: Mapped[str] = mapped_column(Text, default="", server_default="")
    requested_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    requested_by: Mapped[str | None] = mapped_column(String(100))
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    @property
    def netbox_version(self) -> str | None:  # nome di prima, resta nell'API
        return self.source_version if self.source == "netbox" else None
