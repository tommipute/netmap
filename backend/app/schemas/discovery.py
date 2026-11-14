from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

from app.config import settings
from app.discovery.snmp_rules import check_oid, check_regex, clean_oid
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


# ---------- Regole SNMP ----------
def _oid(value: str | None) -> str | None:
    value = clean_oid(value)
    return check_oid(value) if value else None


def _regex(value: str | None) -> str | None:
    value = (value or "").strip()
    return check_regex(value) if value else None


def _kind(value: str | None) -> str | None:
    from app.services.roles import BY_KEY

    if value and value not in BY_KEY:
        raise ValueError(f"Tipo di apparato sconosciuto: {value}")
    return value or None


Oid = Annotated[str | None, Field(max_length=200), AfterValidator(_oid)]
Regex = Annotated[str | None, Field(max_length=500), AfterValidator(_regex)]
IfType = Annotated[int, Field(ge=1, le=65535)]


class SnmpRuleBase(InputSchema):
    name: Name
    enabled: bool = True
    description: str | None = None
    match_object_id: Oid = Field(None, description="Inizio del sysObjectID degli apparati (es. 1.3.6.1.4.1.11863)")
    match_descr: Regex = Field(None, description="Espressione regolare sulla descrizione SNMP (sysDescr)")
    model_oid: Oid = Field(None, description="OID del produttore con il modello")
    model_regex: Regex = Field(None, description="Modello dalla descrizione SNMP: il primo gruppo tra parentesi, o tutto")
    serial_oid: Oid = Field(None, description="OID del produttore con il numero di serie")
    port_name: Literal["name", "descr", "alias"] | None = Field(None, description="Nome delle porte: ifName, ifDescr o ifAlias")
    ignore_ports: Regex = Field(None, description="Porte da ignorare: espressione regolare sul nome")
    ignore_if_types: list[IfType] = Field(default_factory=list, description="Porte da ignorare: ifType (24 loopback, 53 virtuale…)")
    manufacturer: str | None = Field(None, max_length=100)
    kind: Annotated[str | None, AfterValidator(_kind)] = Field(None, description="Tipo di apparato (switch, router, ap…)")
    fdb_port: Literal["position", "ifindex"] | None = Field(
        None, description="Tabella MAC con porte che non sono porte bridge: n-esima porta bridge o ifIndex")
    lldp_port_oid: Oid = Field(None, description="Colonna indicizzata da lldpRemIndex con l'ifIndex della porta locale")


class SnmpRuleCreate(SnmpRuleBase):
    pass


SnmpRuleUpdate = make_partial(SnmpRuleBase, "SnmpRuleUpdate")


class SnmpRuleRead(SnmpRuleCreate, ReadSchema):
    builtin: bool = Field(False, description="Inclusa in NetMap: si può solo spegnere")


class SnmpRuleFile(BaseModel):
    """File delle regole (export / import): stessi campi dell'API, senza id né date."""
    model_config = ConfigDict(extra="forbid")
    netmap: Literal["snmp-rules"] = "snmp-rules"
    version: Literal[1] = 1
    rules: list[SnmpRuleCreate]


class SnmpRuleImportResult(BaseModel):
    created: int
    updated: int


class SnmpRuleTest(BaseModel):
    """Prova di una regola com'è nel modulo, anche non salvata, su un indirizzo."""
    model_config = ConfigDict(extra="forbid")
    host: str = Field(..., max_length=100)
    profile_ids: list[int] = Field(..., min_length=1)
    rule_id: int | None = Field(None, description="Regola in modifica: la sua versione salvata non conta nella prova")
    rule: SnmpRuleCreate = Field(..., description="Campi della regola come in creazione")


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
    host: str | None = None  # rilettura di un solo device


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
    diff: list[list[Any]]  # [campo, attuale, proposto]
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


# ---------- Prova su pochi indirizzi ----------
def _probe_targets(value: list[str]) -> list[str]:
    from app.discovery.probe import MAX_HOSTS
    return validate_targets(value, MAX_HOSTS)


class ProbeRequest(BaseModel):
    targets: Annotated[list[str], AfterValidator(_probe_targets)] = Field(
        ..., min_length=1, description="IP, intervalli o subnet: al massimo 256 indirizzi")
    profile_ids: list[int] = Field(..., min_length=1, description="Profili SNMP da provare, in ordine")


class ProbeAttempt(BaseModel):
    profile: str
    error: str | None = None  # None = ha risposto
    answered: bool  # l'apparato ha risposto, anche se con un errore


class SnmpReportData(BaseModel):
    """Cosa ha letto la scansione da un apparato (discovery/report.py)."""
    host: str
    profile: str | None = None
    sys_name: str | None = None
    sys_object_id: str | None = None
    manufacturer: str | None = None
    sys_descr: str | None = None
    model: str | None = None
    model_source: str | None = Field(None, description="entity, sysdescr, chassis, rule")
    serial: str | None = None
    kind: str | None = Field(None, description="Tipo di apparato riconosciuto (services/roles.py)")
    kind_reason: str | None = None
    rules: list[str] = Field(default_factory=list, description="Regole SNMP che valgono per l'apparato")
    counts: dict[str, int] = Field(description="Righe lette: interfaces, ips, members, lldp, cdp, vlans, port_vlans, fdb, arp")
    fdb_source: str | None = Field(None, description="qbridge, bridge")
    notes: dict[str, int] = Field(
        default_factory=dict,
        description="Adattamenti e righe scartate: bridge_port_ifindex, mac_length_prefix, fdb_on_lag, fdb_unmapped, "
                    "fdb_bad_index, cisco_vlan_fdb, neighbor_no_local_port, renamed_ports, ports_ignored")
    problems: list[str] = Field(default_factory=list, description="Tabelle che non si sono lette, con il motivo")


class SnmpRulePortChange(BaseModel):
    if_index: int
    before: str
    after: str | None = None


class SnmpRuleTestResult(BaseModel):
    host: str
    error: str | None = None  # lettura fallita
    attempts: list[ProbeAttempt] = Field(default_factory=list, description="Se nessun profilo ha risposto: perché")
    matches: bool = False  # la regola vale per questo apparato
    before: SnmpReportData | None = None  # con le regole salvate attive
    after: SnmpReportData | None = None   # con questa regola al posto della sua versione salvata
    ports: list[SnmpRulePortChange] = Field(default_factory=list, description="Porte rinominate o ignorate (after null)")


class SnmpRuleRef(BaseModel):
    id: int
    name: str
    builtin: bool = False
    updated_at: datetime | None = None  # cambiata dopo la lettura: vale dalla prossima


class SnmpReportRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    read_at: datetime
    run_id: int | None = None
    data: SnmpReportData
    # Regole attive che valgono adesso per l'apparato (sysObjectID e descrizione letti): diverse da data.rules se una
    # regola è nuova o cambiata dopo la lettura
    rules_now: list[SnmpRuleRef] = []
    host_run: DiscoveryRunRead | None = None  # rilettura in coda o in corso


class ProbeFound(BaseModel):
    profile: str | None = None
    sys_name: str | None = None
    sys_descr: str | None = None
    sys_object_id: str | None = None
    sys_location: str | None = None
    manufacturer: str | None = None
    model: str | None = None
    model_known: bool
    serial: str | None = None
    kind: str | None = None
    interfaces: int
    ips: int
    neighbors: int
    vlans: int
    members: int
    fdb: int
    arp: int
    problems: list[str]
    device_id: int | None = None
    device_name: str | None = None
    report: SnmpReportData | None = None


class ProbeResult(BaseModel):
    host: str
    ping_ms: float | None = None
    attempts: list[ProbeAttempt]
    error: str | None = None
    found: ProbeFound | None = None
