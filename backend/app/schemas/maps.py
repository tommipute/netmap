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


class MapView(BaseModel):
    map: MapRead
    nodes: list[MapViewNode]
    edges: list[TopologyEdge]
    available: list[TopologyNode]  # device della sede non ancora in mappa (mappe manuali)
    vlans: list[MapVLAN] = []  # VLAN delle porte dei device in mappa
    routes: list[CableRoute] = []  # cavi con i punti di ancoraggio disegnati a mano


class NodePosition(BaseModel):
    device_id: int
    x: float
    y: float
