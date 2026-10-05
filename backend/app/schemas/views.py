"""Schemi delle risposte "calcolate" (vicini, topologia, utilizzo subnet, ricerca)."""
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
    type: str  # device / interface / ip
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
    ips: list[PortIP]


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

