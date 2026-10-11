from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.common import InputSchema, Name, ReadSchema, make_partial
from app.schemas.views import TopologyEdge, TopologyNode


class MapBase(InputSchema):
    name: Name
    location_id: int | None = Field(None, description="Limita la mappa a una posizione (e sotto-posizioni)")
    auto_include: bool = Field(True, description="Mostra sempre tutti i device della sede/posizione")
    description: str | None = None


class MapCreate(MapBase):
    site_id: int


MapUpdate = make_partial(MapBase, "MapUpdate")


class MapRead(MapCreate, ReadSchema):
    pass


class MapViewNode(TopologyNode):
    x: float | None = None  # None = posizione mai salvata
    y: float | None = None


class MapVLAN(BaseModel):
    id: int
    vid: int
    name: str


class RoutePoint(BaseModel):
    x: float
    y: float


class RouteEnd(BaseModel):
    side: Literal["top", "bottom", "left", "right"]
    f: float = Field(ge=0, le=1, description="Posizione lungo il lato (0 = inizio, 1 = fine)")


class CableRoute(BaseModel):
    cable_id: int
    points: list[RoutePoint] = Field([], max_length=50, description="Spigoli del percorso, dal lato A al lato B del cavo")
    a_end: RouteEnd | None = Field(None, description="Dove si attacca il lato A (vuoto = automatico)")
    b_end: RouteEnd | None = None


class MapLocation(BaseModel):
    id: int
    name: str
    parent_id: int | None
    path: str
    floor: int | None


class MapBackgroundRead(BaseModel):
    """Sfondo della mappa: l'immagine si legge da /maps/{id}/background?v={version}."""
    x: float
    y: float
    width: float
    height: float  # dalle proporzioni dell'immagine
    opacity: float
    width_px: int
    height_px: int
    version: int


class MapBackgroundUpdate(InputSchema):
    x: float | None = Field(None, ge=-1_000_000, le=1_000_000)
    y: float | None = Field(None, ge=-1_000_000, le=1_000_000)
    width: float | None = Field(None, gt=10, le=1_000_000)
    opacity: float | None = Field(None, ge=0.05, le=1)


class MapEndpoint(BaseModel):
    """MAC visto su una porta di un device in mappa (PC, telefono, telecamera…)."""

    id: int
    mac: str
    ip: str | None = None
    vlan: int | None = None
    vlan_name: str | None = None
    device_id: int
    interface_id: int
    interface_name: str
    macs_on_port: int | None = None
    last_seen_at: datetime | None = None
    known_as: str | None = None  # come lo conosce la documentazione (nome DNS, porta di un device)
    known_device_id: int | None = None


class MapView(BaseModel):
    map: MapRead
    nodes: list[MapViewNode]
    edges: list[TopologyEdge]
    available: list[TopologyNode]  # device della sede non ancora in mappa (mappe manuali)
    vlans: list[MapVLAN] = []  # VLAN delle porte dei device in mappa
    routes: list[CableRoute] = []  # cavi con i punti di ancoraggio disegnati a mano
    locations: list[MapLocation] = []  # posizioni dei device in mappa con quelle che le contengono (bolle)
    background: MapBackgroundRead | None = None  # immagine di sfondo
    endpoints: list[MapEndpoint] = []  # endpoint sulle porte dei device in mappa (al massimo 3000)
    endpoint_total: int = 0


class NodePosition(BaseModel):
    device_id: int
    x: float
    y: float
