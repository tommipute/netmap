"""Copie dei backup fuori dal server: destinazioni (cartella di rete SMB o SFTP), file già copiati, richieste al worker."""
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, false, func, true
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class BackupTarget(TimestampMixin, Base):
    """Dove il worker copia i backup del database fatti dallo script sull'host (services/offsite.py)."""

    __tablename__ = "backup_targets"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    type: Mapped[str] = mapped_column(String(10))  # smb / sftp
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    host: Mapped[str] = mapped_column(String(255))
    port: Mapped[int | None] = mapped_column(Integer)  # vuota = 445 (SMB) o 22 (SFTP)
    share: Mapped[str | None] = mapped_column(String(255))  # SMB: nome della condivisione
    folder: Mapped[str] = mapped_column(String(500), default="", server_default="")  # cartella dentro la condivisione o sul server
    username: Mapped[str] = mapped_column(String(255))
    # Cifrati con la chiave dei segreti: password (SMB, SFTP) e chiave privata (SFTP, al posto della password)
    secret_enc: Mapped[str | None] = mapped_column(Text)
    private_key_enc: Mapped[str | None] = mapped_column(Text)
    # SFTP: chiave pubblica del server ("ssh-ed25519 AAAA..."), registrata alla prima connessione e poi verificata
    host_key: Mapped[str | None] = mapped_column(Text)
    keep_days: Mapped[int] = mapped_column(Integer, default=30, server_default="30")  # 0 = non cancellare mai
    include_key: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    last_copy_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    last_error_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    description: Mapped[str | None] = mapped_column(Text)

    @property
    def has_secret(self) -> bool:
        return bool(self.secret_enc)

    @property
    def has_private_key(self) -> bool:
        return bool(self.private_key_enc)


class BackupCopy(Base):
    """Un file già copiato su una destinazione: il worker copia solo quelli che mancano."""

    __tablename__ = "backup_copies"
    __table_args__ = (UniqueConstraint("target_id", "file"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    target_id: Mapped[int] = mapped_column(ForeignKey("backup_targets.id", ondelete="CASCADE"), index=True)
    file: Mapped[str] = mapped_column(String(255))
    size: Mapped[int] = mapped_column(BigInteger)
    copied_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class BackupTask(Base):
    """Richiesta dall'interfaccia al worker: "copia ora" o "riporta sul server" un file della destinazione."""

    __tablename__ = "backup_tasks"

    id: Mapped[int] = mapped_column(primary_key=True)
    target_id: Mapped[int] = mapped_column(ForeignKey("backup_targets.id", ondelete="CASCADE"), index=True)
    action: Mapped[str] = mapped_column(String(10))  # sync / fetch
    file: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(10), default="queued", server_default="queued")  # queued/running/done/error
    message: Mapped[str | None] = mapped_column(Text)
    requested_by: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
