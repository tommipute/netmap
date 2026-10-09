from datetime import datetime
from enum import StrEnum

from typing import Annotated, Literal

from pydantic import Field

from app.schemas.common import InputSchema, Name, ReadSchema, make_partial


class AlertType(StrEnum):
    EMAIL = "email"
    WEBHOOK = "webhook"
    TELEGRAM = "telegram"


class SmtpSecurity(StrEnum):
    STARTTLS = "starttls"
    SSL = "ssl"
    NONE = "none"


class WebhookFormat(StrEnum):
    TEXT = "text"
    TEAMS = "teams"


TemplateKey = Literal["down", "up", "port_down", "port_up"]
Template = Annotated[str, Field(max_length=500)]
Ports = Literal["none", "cabled", "selected"]


class AlertChannelBase(InputSchema):
    name: Name
    enabled: bool = True
    delay_minutes: int = Field(5, ge=0, le=1440, description="Minuti di attesa prima di avvisare (un ping perso non conta)")
    notify_recovery: bool = Field(True, description="Avvisa anche quando il device torna a rispondere")
    email_to: list[str] = Field(default_factory=list, description="Destinatari (email)")
    smtp_host: str | None = Field(None, max_length=255)
    smtp_port: int | None = Field(None, ge=1, le=65535)
    smtp_security: SmtpSecurity | None = SmtpSecurity.STARTTLS
    smtp_user: str | None = Field(None, max_length=255)
    smtp_from: str | None = Field(None, max_length=255)
    webhook_format: WebhookFormat | None = WebhookFormat.TEXT
    telegram_chat_id: str | None = Field(None, max_length=100)
    language: Literal["it", "en"] = Field("it", description="Lingua dei messaggi")
    description: str | None = None
    site_ids: list[int] = Field(default_factory=list, description="Avvisa per i device di queste sedi (vuoto = tutte)")
    location_ids: list[int] = Field(default_factory=list, description="... di queste posizioni, con quelle contenute")
    role_ids: list[int] = Field(default_factory=list, description="... con questi ruoli (insieme a sedi e posizioni)")
    device_ids: list[int] = Field(default_factory=list, description="Device in più, sempre compresi")
    ports: Ports = Field("none", description="Porte: nessuna, quelle con un cavo documentato, quelle scelte")
    interface_ids: list[int] = Field(default_factory=list, description="Porte scelte (con ports = selected)")
    templates: dict[TemplateKey, Template] = Field(default_factory=dict, description="Modelli delle righe")
    # Solo scrittura (salvati cifrati): assenti = invariati, vuoti = cancellati
    smtp_password: str | None = Field(None, max_length=255)
    webhook_url: str | None = Field(None, max_length=2000)
    telegram_token: str | None = Field(None, max_length=255)


class AlertChannelCreate(AlertChannelBase):
    type: AlertType


AlertChannelUpdate = make_partial(AlertChannelBase, "AlertChannelUpdate")


class AlertChannelRead(ReadSchema):
    name: str
    type: str
    enabled: bool
    delay_minutes: int
    notify_recovery: bool
    email_to: list[str]
    smtp_host: str | None = None
    smtp_port: int | None = None
    smtp_security: str | None = None
    smtp_user: str | None = None
    smtp_from: str | None = None
    webhook_format: str | None = None
    telegram_chat_id: str | None = None
    language: str = "it"
    description: str | None = None
    site_ids: list[int] = []
    location_ids: list[int] = []
    role_ids: list[int] = []
    device_ids: list[int] = []
    ports: str = "none"
    interface_ids: list[int] = []
    templates: dict[str, str] = {}
    has_secret: bool
    last_sent_at: datetime | None = None
    last_error: str | None = None


class AlertPreviewRequest(InputSchema):
    language: Literal["it", "en"] = "it"
    templates: dict[TemplateKey, Template] = Field(default_factory=dict)
    ports: Ports = "none"
