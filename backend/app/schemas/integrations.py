"""Token API e webhook delle modifiche."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import InputSchema, Name, ReadSchema, make_partial


class ApiTokenCreate(InputSchema):
    name: Name
    read_only: bool = Field(False, description="Solo lettura anche se l'utente può modificare")
    expires_days: int | None = Field(None, ge=1, le=3650, description="Giorni di validità (vuoto = non scade)")
    user_id: int | None = Field(None, description="Utente del token (solo amministratori; vuoto = chi lo crea)")
    description: str | None = None


class ApiTokenRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    prefix: str
    user_id: int
    username: str
    user_role: str
    read_only: bool
    expires_at: datetime | None = None
    expired: bool
    last_used_at: datetime | None = None
    last_used_ip: str | None = None
    description: str | None = None
    created_at: datetime | None = None


class ApiTokenCreated(ApiTokenRead):
    token: str = Field(description="Il token intero: si vede solo adesso")


Action = Literal["create", "update", "delete"]


class WebhookBase(InputSchema):
    name: Name
    enabled: bool = True
    object_types: list[str] = Field(default_factory=list, description="Tipi di oggetto (device, cable, ip…); vuoto = tutti")
    actions: list[Action] = Field(default_factory=list, description="Azioni (create, update, delete); vuoto = tutte")
    verify_tls: bool = True
    description: str | None = None
    # Solo scrittura (salvati cifrati): assenti = invariati, vuoti = cancellati
    url: str | None = Field(None, max_length=2000)
    secret: str | None = Field(None, max_length=255, description="Chiave per la firma X-NetMap-Signature (HMAC-SHA256)")


class WebhookCreate(WebhookBase):
    pass


WebhookUpdate = make_partial(WebhookBase, "WebhookUpdate")


class WebhookRead(ReadSchema):
    name: str
    enabled: bool
    object_types: list[str] = []
    actions: list[str] = []
    verify_tls: bool = True
    description: str | None = None
    url_host: str | None = None
    has_secret: bool
    cursor: int
    last_sent_at: datetime | None = None
    last_error: str | None = None
    last_error_at: datetime | None = None
