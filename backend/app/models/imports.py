"""Import da NetBox: una riga per ogni import (o simulazione) chiesto dall'interfaccia, eseguito dal worker."""
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
    # Token di NetBox cifrato con la chiave dei segreti: serve solo al worker, cancellato a fine import
    token_enc: Mapped[str | None] = mapped_column(Text)
    verify_tls: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    site_ids: Mapped[list] = mapped_column(JSONType, default=list, server_default=text("'[]'"))  # vuoto = tutte
    site_names: Mapped[list] = mapped_column(JSONType, default=list, server_default=text("'[]'"))
    dry_run: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    status: Mapped[str] = mapped_column(
        String(20), default=RunStatus.QUEUED.value, server_default=RunStatus.QUEUED.value, index=True
    )
    # {"device": {"created": 3, "existing": 1, "failed": 0, "skipped": 0}, ...}
    counts: Mapped[dict] = mapped_column(JSONType, default=dict, server_default=text("'{}'"))
    # Oggetti non importati e avvisi: [{"kind": "device", "name": "sw-01", "message": "..."}]
    problems: Mapped[list] = mapped_column(JSONType, default=list, server_default=text("'[]'"))
    netbox_version: Mapped[str | None] = mapped_column(String(50))
    log: Mapped[str] = mapped_column(Text, default="", server_default="")
    requested_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    requested_by: Mapped[str | None] = mapped_column(String(100))
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
