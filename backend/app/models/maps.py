"""Mappe di rete: ogni mappa riguarda una sede (ed eventualmente una posizione)
e salva la posizione dei device disegnati."""
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, LargeBinary, String, Text, true
from sqlalchemy.orm import Mapped, deferred, mapped_column

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
    """Percorso di un cavo sistemato a mano su una mappa.

    points: spigoli del percorso ad angolo (vuoto = percorso automatico); ends: dove si attacca il cavo ai due
    device, {"a": {"side": "bottom", "f": 0.3}, "b": ...} (f = posizione lungo il lato, da 0 a 1; assente = automatico).
    """

    __tablename__ = "map_cable_routes"

    map_id: Mapped[int] = mapped_column(ForeignKey("maps.id", ondelete="CASCADE"), primary_key=True)
    cable_id: Mapped[int] = mapped_column(ForeignKey("cables.id", ondelete="CASCADE"), primary_key=True)
    points: Mapped[list] = mapped_column(JSON)  # [{"x": .., "y": ..}] nell'ordine dal lato A al lato B del cavo
    ends: Mapped[dict | None] = mapped_column(JSON)


class MapBackground(Base):
    """Immagine di sfondo di una mappa (una per mappa: planimetria, schema del CED…).

    Sta nel database, così finisce nei backup. x, y e width sono in coordinate della mappa; l'altezza segue le
    proporzioni dell'immagine (width_px × height_px). uploaded_at cambia a ogni immagine nuova: fa da versione
    nell'indirizzo, così il browser può tenerla in cache.
    """

    __tablename__ = "map_backgrounds"

    map_id: Mapped[int] = mapped_column(ForeignKey("maps.id", ondelete="CASCADE"), primary_key=True)
    content_type: Mapped[str] = mapped_column(String(30))
    data: Mapped[bytes] = deferred(mapped_column(LargeBinary, nullable=False))
    width_px: Mapped[int] = mapped_column(Integer)
    height_px: Mapped[int] = mapped_column(Integer)
    x: Mapped[float] = mapped_column(Float, default=0)
    y: Mapped[float] = mapped_column(Float, default=0)
    width: Mapped[float] = mapped_column(Float)
    opacity: Mapped[float] = mapped_column(Float, default=0.5)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
