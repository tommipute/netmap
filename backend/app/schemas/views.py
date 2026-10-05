"""Schemi delle risposte "calcolate" (vicini, topologia, utilizzo subnet, ricerca)."""
from datetime import datetime

from pydantic import BaseModel


class Neighbor(BaseModel):
    cable_id: int
    cable_status: str
    local_interface_id: int
    local_interface: str
    remote_device_id: int
    remote_device: str
    remote_interface_id: int
    remote_interface: str


class PrefixUtilization(BaseModel):
    prefix: str
    total: int
    used: int
    percent: float


class TopologyNode(BaseModel):
    id: int
    name: str
    status: str
    site_id: int
    location_id: int | None
    role: str | None
    color: str
    level: int
    primary_ip: str | None
    reachable: bool | None = None          # stato live: vuoto = non controllato
    last_check_at: datetime | None = None
    reachable_changed_at: datetime | None = None
    rtt_ms: float | None = None


class TopologyEdge(BaseModel):
    id: int  # id del cavo
    source: int  # id device lato A
    target: int  # id device lato B
    source_interface: str
    target_interface: str
    status: str
    type: str | None
    speed_mbps: int | None


class Topology(BaseModel):
    nodes: list[TopologyNode]
    edges: list[TopologyEdge]


class SearchResult(BaseModel):
    type: str  # device / interface / ip / endpoint
    id: int
    label: str
    detail: str | None = None
    device_id: int | None = None


class PortIP(BaseModel):
    id: int
    address: str
    is_primary: bool


class Port(BaseModel):
    """Interfaccia di un device con cosa c'è collegato dall'altra parte."""

    id: int
    name: str
    type: str
    enabled: bool
    mgmt_only: bool
    oper_status: str | None = None  # up/down dall'ultima scansione
    mode: str | None
    speed_mbps: int | None
    mac_address: str | None
    description: str | None
    lag_id: int | None
    untagged_vlan: int | None  # VID
    tagged_vlans: list[int]    # VID
    cableable: bool
    cable_id: int | None
    cable_type: str | None
    cable_status: str | None
    remote_device_id: int | None
    remote_device: str | None
    remote_interface_id: int | None
    remote_interface: str | None
    ips: list[PortIP]
    endpoints: int = 0  # MAC visti su questa porta nelle tabelle degli switch


class DeviceImportRequest(BaseModel):
    csv_data: str
    update_existing: bool = True
    dry_run: bool = False


class DeviceImportError(BaseModel):
    row: int
    device: str | None = None
    error: str


class DeviceImportResult(BaseModel):
    total_rows: int
    created_count: int
    updated_count: int
    skipped_count: int
    errors: list[DeviceImportError]
    created_devices: list[str]
    updated_devices: list[str]
    skipped_devices: list[str]
    dry_run: bool



# ---------- Fase 4 ----------
class EndpointRead(BaseModel):
    """Dove è collegato un MAC: switch, porta, luogo e cosa ne sa già la documentazione."""

    id: int
    mac: str
    ip: str | None = None
    vlan: int | None = None
    vlan_name: str | None = None
    device_id: int | None = None
    device_name: str | None = None
    interface_id: int | None = None
    interface_name: str | None = None
    interface_description: str | None = None
    site: str | None = None
    location: str | None = None
    rack: str | None = None
    macs_on_port: int | None = None
    previous_device_name: str | None = None
    previous_interface_name: str | None = None
    moved_at: datetime | None = None
    first_seen_at: datetime | None = None
    last_seen_at: datetime | None = None
    ip_seen_at: datetime | None = None
    known_as: str | None = None
    known_device_id: int | None = None


class StatusSummary(BaseModel):
    up: int
    down: int
    unknown: int
    last_check_at: datetime | None = None
    interval_seconds: int


class CheckResult(BaseModel):
    checked: int
    up: int
    down: int


class RackDevice(BaseModel):
    id: int
    name: str
    position: int | None
    u_height: int
    face_label: str | None = None  # modello
    role: str | None = None
    color: str
    status: str
    reachable: bool | None = None
    conflict: bool = False  # si sovrappone a un altro device o esce dal rack


class RackElevation(BaseModel):
    rack_id: int
    name: str
    u_height: int
    used_units: int
    devices: list[RackDevice]   # con posizione
    unplaced: list[RackDevice]  # nel rack ma senza unità indicata
