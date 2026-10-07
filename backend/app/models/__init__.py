"""Importa tutti i modelli: Alembic li trova da qui."""
from sqlalchemy import select
from sqlalchemy.orm import column_property

from app.models.alerts import AlertChannel, AlertState
from app.models.audit import AuditEntry
from app.models.auth import User
from app.models.base import Base
from app.models.dcim import (
    Cable,
    Device,
    DeviceRole,
    DeviceType,
    Interface,
    Location,
    Manufacturer,
    Rack,
    Site,
    StackMember,
    interface_tagged_vlans,
)
from app.models.discovery import DiscoveryChange, DiscoveryJob, DiscoveryRun, SnmpProfile
from app.models.ipam import VLAN, VRF, IPAddress, Prefix
from app.models.maps import MapCableRoute, MapNode, NetworkMap
from app.models.monitoring import Endpoint

# IP di management del device in sola lettura (scheda e modulo del device, interfacce). Sta qui perché unisce
# modelli di dcim e ipam; lo scrive services.rules.set_management_ip.
Device.management_ip = column_property(
    select(IPAddress.address)
    .join(Interface, IPAddress.interface_id == Interface.id)
    .where(Interface.device_id == Device.id, IPAddress.is_primary.is_(True))
    .correlate_except(IPAddress, Interface)
    .limit(1)
    .scalar_subquery()
)

__all__ = [
    "AlertChannel",
    "AlertState",
    "AuditEntry",
    "Base",
    "Cable",
    "Device",
    "DeviceRole",
    "DeviceType",
    "DiscoveryChange",
    "DiscoveryJob",
    "DiscoveryRun",
    "Endpoint",
    "Interface",
    "IPAddress",
    "Location",
    "Manufacturer",
    "MapCableRoute",
    "MapNode",
    "NetworkMap",
    "Prefix",
    "Rack",
    "Site",
    "StackMember",
    "SnmpProfile",
    "User",
    "VLAN",
    "VRF",
    "interface_tagged_vlans",
]
