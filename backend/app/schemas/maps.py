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


class MapView(BaseModel):
    map: MapRead
    nodes: list[MapViewNode]
    edges: list[TopologyEdge]
    available: list[TopologyNode]  # device della sede non ancora in mappa (mappe manuali)


class NodePosition(BaseModel):
    device_id: int
    x: float
    y: float
