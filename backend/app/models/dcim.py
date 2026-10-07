"""Infrastruttura: sedi, posizioni, rack, produttori, modelli, ruoli, device, interfacce e cavi."""
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Table,
    Text,
    UniqueConstraint,
    false,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, CustomFieldsMixin, DiscoveryMixin, TimestampMixin
from app.models.enums import CableStatus, DeviceStatus, InterfaceType

if TYPE_CHECKING:
    from app.models.ipam import VLAN


class Site(TimestampMixin, CustomFieldsMixin, Base):
    __tablename__ = "sites"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    address: Mapped[str | None] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)


class Location(TimestampMixin, CustomFieldsMixin, Base):
    """Edificio / piano / stanza dentro una sede. Gerarchia libera tramite parent_id."""

    __tablename__ = "locations"
    __table_args__ = (UniqueConstraint("site_id", "parent_id", "name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    site_id: Mapped[int] = mapped_column(ForeignKey("sites.id", ondelete="RESTRICT"), index=True)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("locations.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(Text)


class Rack(TimestampMixin, CustomFieldsMixin, Base):
    __tablename__ = "racks"
    __table_args__ = (UniqueConstraint("site_id", "name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    site_id: Mapped[int] = mapped_column(ForeignKey("sites.id", ondelete="RESTRICT"), index=True)
    location_id: Mapped[int | None] = mapped_column(ForeignKey("locations.id", ondelete="SET NULL"))
    name: Mapped[str] = mapped_column(String(100))
    u_height: Mapped[int] = mapped_column(Integer, default=42, server_default="42")
    description: Mapped[str | None] = mapped_column(Text)


class Manufacturer(TimestampMixin, Base):
    __tablename__ = "manufacturers"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)


class DeviceType(TimestampMixin, CustomFieldsMixin, Base):
    """Modello di apparato (es. Cisco Catalyst 9300-48P)."""

    __tablename__ = "device_types"
    __table_args__ = (UniqueConstraint("manufacturer_id", "model"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    manufacturer_id: Mapped[int] = mapped_column(ForeignKey("manufacturers.id", ondelete="RESTRICT"))
    model: Mapped[str] = mapped_column(String(100))
    part_number: Mapped[str | None] = mapped_column(String(100))
    u_height: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    # sysObjectID SNMP: in fase 3 serve a riconoscere il modello in automatico
    sys_object_id: Mapped[str | None] = mapped_column(String(255), unique=True)
    # Ruolo dei device di questo modello che non ne hanno uno (anche quelli trovati dalla scansione)
    default_role_id: Mapped[int | None] = mapped_column(ForeignKey("device_roles.id", ondelete="SET NULL"))
    description: Mapped[str | None] = mapped_column(Text)


class DeviceRole(TimestampMixin, Base):
    """Ruolo (firewall, core, accesso, AP...). Colore e livello servono alla mappa."""

    __tablename__ = "device_roles"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    color: Mapped[str] = mapped_column(String(7), default="#888780", server_default="#888780")
    # Livello nella mappa gerarchica automatica: 0 = in alto, numeri più alti = più in basso
    level: Mapped[int] = mapped_column(Integer, default=2, server_default="2")
    description: Mapped[str | None] = mapped_column(Text)


class Device(TimestampMixin, CustomFieldsMixin, DiscoveryMixin, Base):
    __tablename__ = "devices"
    __table_args__ = (UniqueConstraint("site_id", "name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    site_id: Mapped[int] = mapped_column(ForeignKey("sites.id", ondelete="RESTRICT"), index=True)
    location_id: Mapped[int | None] = mapped_column(ForeignKey("locations.id", ondelete="SET NULL"))
    rack_id: Mapped[int | None] = mapped_column(ForeignKey("racks.id", ondelete="SET NULL"))
    rack_position: Mapped[int | None] = mapped_column(Integer)
    # Modello e ruolo opzionali: un device trovato via SNMP può non averli ancora
    device_type_id: Mapped[int | None] = mapped_column(ForeignKey("device_types.id", ondelete="RESTRICT"))
    role_id: Mapped[int | None] = mapped_column(ForeignKey("device_roles.id", ondelete="RESTRICT"))
    status: Mapped[str] = mapped_column(
        String(20), default=DeviceStatus.ACTIVE.value, server_default=DeviceStatus.ACTIVE.value
    )
    serial: Mapped[str | None] = mapped_column(String(100), index=True)
    asset_tag: Mapped[str | None] = mapped_column(String(100), unique=True)
    sys_name: Mapped[str | None] = mapped_column(String(255))
    sys_descr: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    # Stato live (fase 4): l'ultimo controllo del monitor (ping e SNMP sull'IP di management)
    reachable: Mapped[bool | None] = mapped_column(Boolean)          # vuoto = mai controllato
    last_check_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reachable_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rtt_ms: Mapped[float | None] = mapped_column(Float)
    # Profilo SNMP che ha risposto all'ultima scansione: il monitor lo usa per leggere lo stato delle porte
    snmp_profile_id: Mapped[int | None] = mapped_column(ForeignKey("snmp_profiles.id", ondelete="SET NULL"))


class StackMember(TimestampMixin, DiscoveryMixin, Base):
    """Uno switch di uno stack. Lo stack è un solo device (un IP, una configurazione, porte Gi1/0/x, Gi2/0/x...):
    qui ci sono i singoli switch fisici, con seriale, modello e unità nel rack del device."""

    __tablename__ = "stack_members"
    __table_args__ = (UniqueConstraint("device_id", "number"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"), index=True)
    number: Mapped[int] = mapped_column(Integer)  # numero del membro (1 = Gi1/0/x...)
    model: Mapped[str | None] = mapped_column(String(100))
    serial: Mapped[str | None] = mapped_column(String(100), index=True)
    rack_position: Mapped[int | None] = mapped_column(Integer)  # unità più bassa, nel rack del device
    description: Mapped[str | None] = mapped_column(Text)

    device: Mapped["Device"] = relationship(lazy="joined")

    @property
    def device_name(self) -> str | None:
        return self.device.name if self.device else None


interface_tagged_vlans = Table(
    "interface_tagged_vlans",
    Base.metadata,
    Column("interface_id", ForeignKey("interfaces.id", ondelete="CASCADE"), primary_key=True),
    Column("vlan_id", ForeignKey("vlans.id", ondelete="CASCADE"), primary_key=True),
)


class Interface(TimestampMixin, CustomFieldsMixin, DiscoveryMixin, Base):
    __tablename__ = "interfaces"
    __table_args__ = (UniqueConstraint("device_id", "name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    type: Mapped[str] = mapped_column(
        String(20), default=InterfaceType.COPPER.value, server_default=InterfaceType.COPPER.value
    )
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    mgmt_only: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    mac_address: Mapped[str | None] = mapped_column(String(17), index=True)
    speed_mbps: Mapped[int | None] = mapped_column(Integer)
    mtu: Mapped[int | None] = mapped_column(Integer)
    mode: Mapped[str | None] = mapped_column(String(10))  # access / trunk / vuoto = routed
    untagged_vlan_id: Mapped[int | None] = mapped_column(ForeignKey("vlans.id", ondelete="SET NULL"))
    lag_id: Mapped[int | None] = mapped_column(ForeignKey("interfaces.id", ondelete="SET NULL"))
    if_index: Mapped[int | None] = mapped_column(Integer)         # ifIndex SNMP
    oper_status: Mapped[str | None] = mapped_column(String(10))   # up/down dall'ultimo poll
    description: Mapped[str | None] = mapped_column(Text)

    device: Mapped["Device"] = relationship(lazy="joined")
    tagged_vlans: Mapped[list["VLAN"]] = relationship(secondary=interface_tagged_vlans, order_by="VLAN.vid")

    @property
    def tagged_vlan_ids(self) -> list[int]:
        return [vlan.id for vlan in self.tagged_vlans]

    @property
    def device_name(self) -> str | None:
        return self.device.name if self.device else None

    @property
    def device_management_ip(self) -> str | None:
        """IP di management del device di questa porta (ce n'è uno solo per device)."""
        return self.device.management_ip if self.device else None


class Cable(TimestampMixin, CustomFieldsMixin, DiscoveryMixin, Base):
    """Collegamento fisico tra due interfacce. La mappa di rete è costruita da qui."""

    __tablename__ = "cables"
    __table_args__ = (CheckConstraint("a_interface_id <> b_interface_id", name="distinct_ends"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    a_interface_id: Mapped[int] = mapped_column(ForeignKey("interfaces.id", ondelete="CASCADE"), unique=True)
    b_interface_id: Mapped[int] = mapped_column(ForeignKey("interfaces.id", ondelete="CASCADE"), unique=True)
    type: Mapped[str | None] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(
        String(20), default=CableStatus.CONNECTED.value, server_default=CableStatus.CONNECTED.value
    )
    label: Mapped[str | None] = mapped_column(String(100))
    color: Mapped[str | None] = mapped_column(String(7))
    length: Mapped[float | None] = mapped_column(Float)
    length_unit: Mapped[str] = mapped_column(String(5), default="m", server_default="m")
    description: Mapped[str | None] = mapped_column(Text)

    a_interface: Mapped["Interface"] = relationship(foreign_keys=[a_interface_id], lazy="joined")
    b_interface: Mapped["Interface"] = relationship(foreign_keys=[b_interface_id], lazy="joined")

    # Nomi già risolti, comodi per elenchi e mappe
    @property
    def a_device_id(self) -> int:
        return self.a_interface.device_id

    @property
    def a_device_name(self) -> str:
        return self.a_interface.device.name

    @property
    def a_interface_name(self) -> str:
        return self.a_interface.name

    @property
    def b_device_id(self) -> int:
        return self.b_interface.device_id

    @property
    def b_device_name(self) -> str:
        return self.b_interface.device.name

    @property
    def b_interface_name(self) -> str:
        return self.b_interface.name
