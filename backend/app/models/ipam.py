"""IPAM: VRF, VLAN, prefissi e indirizzi IP."""
import ipaddress
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    false,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from app.core.net import ip_sort_key, normalize_ip_interface, normalize_prefix, prefix_sort_key
from app.models.base import Base, CustomFieldsMixin, DiscoveryMixin, TimestampMixin
from app.models.enums import IPAddressStatus, IPAMStatus

if TYPE_CHECKING:
    from app.models.dcim import Interface


class VRF(TimestampMixin, CustomFieldsMixin, Base):
    __tablename__ = "vrfs"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    rd: Mapped[str | None] = mapped_column(String(50), unique=True)
    description: Mapped[str | None] = mapped_column(Text)


class VLAN(TimestampMixin, CustomFieldsMixin, Base):
    """site_id vuoto = VLAN globale, valida per tutte le sedi."""

    __tablename__ = "vlans"
    __table_args__ = (
        UniqueConstraint("site_id", "vid"),
        CheckConstraint("vid BETWEEN 1 AND 4094", name="vid_range"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    site_id: Mapped[int | None] = mapped_column(ForeignKey("sites.id", ondelete="RESTRICT"), index=True)
    vid: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(
        String(20), default=IPAMStatus.ACTIVE.value, server_default=IPAMStatus.ACTIVE.value
    )
    description: Mapped[str | None] = mapped_column(Text)


class Prefix(TimestampMixin, CustomFieldsMixin, Base):
    __tablename__ = "prefixes"
    __table_args__ = (UniqueConstraint("vrf_id", "prefix"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    prefix: Mapped[str] = mapped_column(String(50))
    sort_key: Mapped[bytes] = mapped_column(LargeBinary(18), index=True)
    vrf_id: Mapped[int | None] = mapped_column(ForeignKey("vrfs.id", ondelete="RESTRICT"))
    site_id: Mapped[int | None] = mapped_column(ForeignKey("sites.id", ondelete="SET NULL"))
    vlan_id: Mapped[int | None] = mapped_column(ForeignKey("vlans.id", ondelete="SET NULL"))
    status: Mapped[str] = mapped_column(
        String(20), default=IPAMStatus.ACTIVE.value, server_default=IPAMStatus.ACTIVE.value
    )
    description: Mapped[str | None] = mapped_column(Text)

    @validates("prefix")
    def _on_prefix(self, _key: str, value: str) -> str:
        value = normalize_prefix(value)
        self.sort_key = prefix_sort_key(ipaddress.ip_network(value))
        return value


class IPAddress(TimestampMixin, CustomFieldsMixin, DiscoveryMixin, Base):
    __tablename__ = "ip_addresses"
    __table_args__ = (UniqueConstraint("vrf_id", "host"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    address: Mapped[str] = mapped_column(String(50))           # con maschera: 10.0.0.5/24
    host: Mapped[str] = mapped_column(String(45), index=True)  # senza maschera: 10.0.0.5
    sort_key: Mapped[bytes] = mapped_column(LargeBinary(17), index=True)
    vrf_id: Mapped[int | None] = mapped_column(ForeignKey("vrfs.id", ondelete="RESTRICT"))
    interface_id: Mapped[int | None] = mapped_column(ForeignKey("interfaces.id", ondelete="SET NULL"), index=True)
    # IP principale (di management) del device a cui appartiene l'interfaccia
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    status: Mapped[str] = mapped_column(
        String(20), default=IPAddressStatus.ACTIVE.value, server_default=IPAddressStatus.ACTIVE.value
    )
    dns_name: Mapped[str | None] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)

    interface: Mapped[Optional["Interface"]] = relationship(lazy="joined")

    @property
    def interface_name(self) -> str | None:
        return self.interface.name if self.interface else None

    @property
    def device_id(self) -> int | None:
        return self.interface.device_id if self.interface else None

    @property
    def device_name(self) -> str | None:
        return self.interface.device.name if self.interface else None

    @validates("address")
    def _on_address(self, _key: str, value: str) -> str:
        iface = ipaddress.ip_interface(normalize_ip_interface(value))
        self.host = str(iface.ip)
        self.sort_key = ip_sort_key(iface.ip)
        return str(iface)
