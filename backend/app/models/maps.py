"""Mappe di rete: ogni mappa riguarda una sede (ed eventualmente una posizione)
e salva la posizione dei device disegnati."""
from sqlalchemy import JSON, Boolean, Float, ForeignKey, String, Text, true
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class NetworkMap(TimestampMixin, Base):
    __tablename__ = "maps"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    site_id: Mapped[int] = mapped_column(ForeignKey("sites.id", ondelete="CASCADE"), index=True)
    # Se valorizzata, la mappa considera solo i device di quella posizione (e delle sotto-posizioni)
    location_id: Mapped[int | None] = mapped_column(ForeignKey("locations.id", ondelete="SET NULL"))
    # True = mostra sempre tutti i device della sede/posizione; False = solo quelli aggiunti a mano
    auto_include: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    description: Mapped[str | None] = mapped_column(Text)


class MapNode(Base):
    """Posizione salvata di un device su una mappa."""

    __tablename__ = "map_nodes"

    map_id: Mapped[int] = mapped_column(ForeignKey("maps.id", ondelete="CASCADE"), primary_key=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"), primary_key=True)
    x: Mapped[float] = mapped_column(Float)
    y: Mapped[float] = mapped_column(Float)


class MapCableRoute(Base):
    """Punti di ancoraggio disegnati a mano per un cavo su una mappa: il cavo passa da lì invece del percorso automatico."""

    __tablename__ = "map_cable_routes"

    map_id: Mapped[int] = mapped_column(ForeignKey("maps.id", ondelete="CASCADE"), primary_key=True)
    cable_id: Mapped[int] = mapped_column(ForeignKey("cables.id", ondelete="CASCADE"), primary_key=True)
    points: Mapped[list] = mapped_column(JSON)  # [{"x": .., "y": ..}] nell'ordine dal lato A al lato B del cavo
