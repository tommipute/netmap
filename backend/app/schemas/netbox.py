"""Import da NetBox e dagli altri programmi: connessione, richiesta e stato degli import."""
from datetime import datetime
from typing import Any, Literal

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


ImportSource = Literal["netbox", "zabbix", "librenms", "observium", "prtg", "glpi", "lansweeper"]


class SourceConnection(BaseModel):
    source: ImportSource
    url: str = Field("", max_length=500, description="Indirizzo del programma (Lansweeper: vuoto = API cloud)")
    token: str = Field(..., min_length=1, max_length=2000, description="Token API, oppure la password se c'è l'utente")
    username: str | None = Field(None, max_length=255, description="Utente (Zabbix, Observium, PRTG, GLPI)")
    app_token: str | None = Field(None, max_length=500, description="App-Token del client API (GLPI)")
    verify_tls: bool = Field(True, description="Verifica il certificato HTTPS")


class SourceGroup(BaseModel):
    id: int | str
    name: str
    devices: int


class SourceProbe(BaseModel):
    version: str
    counts: dict[str, int]
    groups: list[SourceGroup]


class SourceImportCreate(SourceConnection):
    group_ids: list[int | str] = Field(default_factory=list, description="Sedi o gruppi da importare (vuoto = tutti)")
    default_site: str | None = Field(None, max_length=100, description="Sede dei device che non ne hanno una")
    dry_run: bool = Field(True, description="Simulazione: mostra cosa succederebbe senza salvare niente")


class ImportRunSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source: str
    url: str
    verify_tls: bool
    username: str | None = None
    site_ids: list[int | str]
    site_names: list[str]
    dry_run: bool
    status: str
    counts: dict[str, Any]
    source_version: str | None = None
    netbox_version: str | None = None  # nome di prima (solo per NetBox)
    default_site: str | None = None
    requested_by: str | None = None
    requested_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None


class ImportRunRead(ImportRunSummary):
    problems: list[dict[str, Any]]
    log: str
