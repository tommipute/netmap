"""Import da NetBox: connessione, richiesta e stato degli import."""
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class NetBoxConnection(BaseModel):
    url: str = Field(..., min_length=1, max_length=500, description="Indirizzo di NetBox, es. https://netbox.azienda.local")
    token: str = Field(..., min_length=1, max_length=500, description="Token API (basta in sola lettura)")
    verify_tls: bool = Field(True, description="Verifica il certificato HTTPS di NetBox")


class NetBoxSite(BaseModel):
    id: int
    name: str
    devices: int


class NetBoxProbe(BaseModel):
    version: str
    counts: dict[str, int]
    sites: list[NetBoxSite]


class NetBoxImportCreate(NetBoxConnection):
    site_ids: list[int] = Field(default_factory=list, description="Sedi di NetBox da importare (vuoto = tutte)")
    dry_run: bool = Field(True, description="Simulazione: mostra cosa succederebbe senza salvare niente")


class ImportRunSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source: str
    url: str
    verify_tls: bool
    site_ids: list[int]
    site_names: list[str]
    dry_run: bool
    status: str
    counts: dict[str, Any]
    netbox_version: str | None = None
    requested_by: str | None = None
    requested_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None


class ImportRunRead(ImportRunSummary):
    problems: list[dict[str, Any]]
    log: str
