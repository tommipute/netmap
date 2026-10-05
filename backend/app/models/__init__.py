"""Importa tutti i modelli: Alembic li trova da qui."""
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
    interface_tagged_vlans,
)
from app.models.discovery import DiscoveryChange, DiscoveryJob, DiscoveryRun, SnmpProfile
from app.models.ipam import VLAN, VRF, IPAddress, Prefix
from app.models.maps import MapNode, NetworkMap

__all__ = [
    "Base",
    "Cable",
    "Device",
    "DeviceRole",
    "DeviceType",
    "DiscoveryChange",
    "DiscoveryJob",
    "DiscoveryRun",
    "Interface",
    "IPAddress",
    "Location",
    "Manufacturer",
    "MapNode",
    "NetworkMap",
    "Prefix",
    "Rack",
    "Site",
    "SnmpProfile",
    "VLAN",
    "VRF",
    "interface_tagged_vlans",
]
