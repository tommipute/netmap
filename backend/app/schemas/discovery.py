from datetime import datetime
from typing import Annotated, Any

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

from app.config import settings
from app.discovery.targets import validate_targets
from app.models.enums import SnmpAuthProtocol, SnmpPrivProtocol, SnmpVersion
from app.schemas.common import InputSchema, Name, ReadSchema, make_partial


def _targets(value: list[str]) -> list[str]:
    return validate_targets(value, settings.discovery_max_hosts)


TargetList = Annotated[list[str], AfterValidator(_targets)]
SecretKey = Annotated[str, Field(min_length=8, max_length=255)]


# ---------- Profili SNMP ----------
class SnmpProfileBase(InputSchema):
    name: Name
    version: SnmpVersion = SnmpVersion.V2C
    port: int = Field(161, ge=1, le=65535)
    timeout: float = Field(2.0, gt=0, le=30, description="Secondi di attesa per ogni richiesta")
    retries: int = Field(1, ge=0, le=5)
    community: str | None = Field(None, max_length=255, description="Solo scrittura: non viene mai restituita")
    username: str | None = Field(None, max_length=100)
    auth_protocol: SnmpAuthProtocol | None = None
    auth_key: SecretKey | None = Field(None, description="Solo scrittura, almeno 8 caratteri")
    priv_protocol: SnmpPrivProtocol | None = None
    priv_key: SecretKey | None = Field(None, description="Solo scrittura, almeno 8 caratteri")
    context_name: str | None = Field(None, max_length=100, description="SNMPv3, di solito vuoto")
    description: str | None = None


class SnmpProfileCreate(SnmpProfileBase):
    pass


SnmpProfileUpdate = make_partial(SnmpProfileBase, "SnmpProfileUpdate")


class SnmpProfileRead(ReadSchema):
    name: str
    version: str
    port: int
    timeout: float
    retries: int
    username: str | None = None
    auth_protocol: str | None = None
    priv_protocol: str | None = None
    context_name: str | None = None
    description: str | None = None
    has_community: bool
    has_auth_key: bool
    has_priv_key: bool


# ---------- Job di scansione ----------
class DiscoveryJobBase(InputSchema):
    name: Name
    targets: TargetList = Field(..., min_length=1, description="Subnet, IP singoli o intervalli: 10.0.0.0/24, 10.0.1.5, 10.0.2.1-50")
    profile_ids: list[int] = Field(..., min_length=1, description="Profili SNMP da provare, in ordine")
    site_id: int = Field(..., description="Sede in cui creare i device nuovi")
    enabled: bool = True
    interval_hours: int | None = Field(None, ge=1, le=720, description="Ogni quante ore ripetere la scansione; vuoto = solo a mano")
    auto_new_interfaces: bool = Field(False, description="Aggiunge da solo le porte nuove dei device già censiti")
    auto_new_ips: bool = Field(False, description="Aggiunge da solo gli IP nuovi sulle porte già censite")
    description: str | None = None


class DiscoveryJobCreate(DiscoveryJobBase):
    pass


DiscoveryJobUpdate = make_partial(DiscoveryJobBase, "DiscoveryJobUpdate")


class DiscoveryJobRead(DiscoveryJobCreate, ReadSchema):
    targets: list[str]  # in lettura niente validazione


# ---------- Esecuzioni e modifiche ----------
class DiscoveryRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    job_id: int
    status: str
    requested_at: datetime | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    hosts_total: int
    hosts_responded: int
    changes_proposed: int
    changes_applied: int
    log: str = ""


class DiscoveryChangeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    run_id: int
    job_id: int
    host: str
    device_id: int | None = None
    device_label: str
    object_type: str
    action: str
    object_id: int | None = None
    summary: str
    data: dict[str, Any]
    diff: dict[str, Any]
    status: str
    auto: bool
    error: str | None = None
    created_at: datetime | None = None
    decided_at: datetime | None = None


class ChangeIds(BaseModel):
    ids: list[int] = Field(..., min_length=1, max_length=10000)


class ApproveResult(BaseModel):
    applied: int
    failed: list[dict[str, Any]]


class RejectResult(BaseModel):
    rejected: int


class PendingCount(BaseModel):
    pending: int
