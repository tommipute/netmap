"""Avvisi quando un device smette di rispondere (e quando torna): canali di invio e stato degli avvisi mandati."""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, true
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, JSONType, TimestampMixin


class AlertChannel(TimestampMixin, Base):
    """Un modo di avvisare: email (SMTP), webhook (Teams, Slack, Mattermost...) o Telegram."""

    __tablename__ = "alert_channels"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    type: Mapped[str] = mapped_column(String(20))  # email / webhook / telegram
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    delay_minutes: Mapped[int] = mapped_column(Integer, default=5, server_default="5")  # niente avviso per un ping perso
    notify_recovery: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    # Email
    email_to: Mapped[list] = mapped_column(JSONType, default=list)
    smtp_host: Mapped[str | None] = mapped_column(String(255))
    smtp_port: Mapped[int | None] = mapped_column(Integer)
    smtp_security: Mapped[str | None] = mapped_column(String(10))  # starttls / ssl / none
    smtp_user: Mapped[str | None] = mapped_column(String(255))
    smtp_from: Mapped[str | None] = mapped_column(String(255))
    # Webhook: "text" = {"text": ...} (Slack, Mattermost, Google Chat, vecchio connettore Teams), "teams" = scheda
    # adattiva per i webhook dei Workflows di Teams
    webhook_format: Mapped[str | None] = mapped_column(String(10))
    # Telegram
    telegram_chat_id: Mapped[str | None] = mapped_column(String(100))
    # Segreto cifrato: password SMTP, indirizzo del webhook (contiene la chiave) o token del bot Telegram
    secret_enc: Mapped[str | None] = mapped_column(Text)
    last_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)

    @property
    def has_secret(self) -> bool:
        return bool(self.secret_enc)


class AlertState(Base):
    """Per ogni canale, i device per cui è già partito l'avviso "non risponde" (per non ripeterlo e per dire quando tornano)."""

    __tablename__ = "alert_states"
    __table_args__ = (UniqueConstraint("channel_id", "device_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    channel_id: Mapped[int] = mapped_column(ForeignKey("alert_channels.id", ondelete="CASCADE"), index=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"), index=True)
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    down_since: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # per dire quanto è stato giù
