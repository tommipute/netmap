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
    # Lingua dei messaggi: it / en (services/alerts.py, TEXTS)
    language: Mapped[str] = mapped_column(String(2), default="it", server_default="it")
    # Segreto cifrato: password SMTP, indirizzo del webhook (contiene la chiave) o token del bot Telegram
    secret_enc: Mapped[str | None] = mapped_column(Text)
    last_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    # Per chi avvisa: tutto vuoto = tutti i device. Sedi e posizioni (con quelle contenute) dicono dove, i ruoli
    # cosa; se ci sono tutti e due valgono insieme. I device scelti si aggiungono sempre.
    site_ids: Mapped[list] = mapped_column(JSONType, default=list, server_default="[]")
    location_ids: Mapped[list] = mapped_column(JSONType, default=list, server_default="[]")
    role_ids: Mapped[list] = mapped_column(JSONType, default=list, server_default="[]")
    device_ids: Mapped[list] = mapped_column(JSONType, default=list, server_default="[]")
    # Porte: none / cabled (quelle con un cavo documentato, dei device qui sopra) / selected (interface_ids)
    ports: Mapped[str] = mapped_column(String(10), default="none", server_default="none")
    interface_ids: Mapped[list] = mapped_column(JSONType, default=list, server_default="[]")
    # Modelli dei messaggi (down, up, port_down, port_up): chiave assente = testo predefinito della lingua
    templates: Mapped[dict] = mapped_column(JSONType, default=dict, server_default="{}")

    @property
    def has_secret(self) -> bool:
        return bool(self.secret_enc)


class AlertState(Base):
    """Per ogni canale, i device e le porte già segnalati giù (per non ripetere l'avviso e dire quando tornano)."""

    __tablename__ = "alert_states"
    __table_args__ = (UniqueConstraint("channel_id", "device_id", "interface_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    channel_id: Mapped[int] = mapped_column(ForeignKey("alert_channels.id", ondelete="CASCADE"), index=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"), index=True)
    # Avviso di una porta (device_id è il suo device); vuoto = avviso del device
    interface_id: Mapped[int | None] = mapped_column(ForeignKey("interfaces.id", ondelete="CASCADE"), index=True)
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    down_since: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # per dire quanto è stato giù
