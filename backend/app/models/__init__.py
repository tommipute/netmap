"""Importa tutti i modelli: Alembic li trova da qui."""
from sqlalchemy import Boolean, select
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import column_property
from sqlalchemy.sql.expression import FunctionElement

from app.models.alerts import AlertChannel, AlertState
from app.models.audit import AuditEntry
from app.models.auth import DirectorySettings, User
from app.models.backups import BackupCopy, BackupTarget, BackupTask
from app.models.base import Base
from app.models.custom_fields import CustomFieldDefinition
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
from app.models.imports import ImportRun
from app.models.ipam import VLAN, VRF, IPAddress, Prefix
from app.models.maps import MapCableRoute, MapNode, NetworkMap
from app.models.monitoring import Endpoint


class in_subquery(FunctionElement):
    """colonna IN (sottoquery). Su Postgres = ANY(ARRAY(...)): così il planner cerca per indice le poche righe
    della sottoquery invece di scorrere tutta la tabella per ogni riga di fuori (es. ordinare migliaia di device
    per IP di management: da mezzo secondo a qualche decina di millisecondi)."""

    type = Boolean()
    inherit_cache = True


@compiles(in_subquery)
def _in_subquery(element, compiler, **kw):
    column, subquery = element.clauses
    return f"{compiler.process(column, **kw)} IN {compiler.process(subquery, **kw)}"


@compiles(in_subquery, "postgresql")
def _in_subquery_postgresql(element, compiler, **kw):
    column, subquery = element.clauses
    return f"{compiler.process(column, **kw)} = ANY(ARRAY{compiler.process(subquery, **kw)})"


def _primary_ip(column):
    """Sottoquery correlata: colonna dell'IP primario (di management) del device."""
    device_ports = select(Interface.id).where(Interface.device_id == Device.id).correlate(Device).scalar_subquery()
    return (
        select(column)
        .where(IPAddress.is_primary.is_(True), in_subquery(IPAddress.interface_id, device_ports))
        .correlate_except(IPAddress, Interface)
        .limit(1)
        .scalar_subquery()
    )


# IP di management del device in sola lettura (scheda e modulo del device, interfacce). Sta qui perché unisce
# modelli di dcim e ipam; lo scrive services.rules.set_management_ip.
Device.management_ip = column_property(_primary_ip(IPAddress.address))
# Per ordinare i device come gli IP (10.0.0.2 prima di 10.0.0.10) e non come testo; si carica solo se serve
Device.management_ip_key = column_property(_primary_ip(IPAddress.sort_key), deferred=True)

__all__ = [
    "AlertChannel",
    "AlertState",
    "AuditEntry",
    "BackupCopy",
    "BackupTarget",
    "BackupTask",
    "Base",
    "Cable",
    "CustomFieldDefinition",
    "Device",
    "DeviceRole",
    "DeviceType",
    "DirectorySettings",
    "DiscoveryChange",
    "DiscoveryJob",
    "DiscoveryRun",
    "Endpoint",
    "ImportRun",
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
