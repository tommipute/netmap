"""Valori ammessi per stati e tipi. Nel DB sono salvati come semplici stringhe,
così aggiungere un valore non richiede migration."""
from enum import StrEnum


class Source(StrEnum):
    MANUAL = "manual"
    SNMP = "snmp"


class DeviceStatus(StrEnum):
    ACTIVE = "active"
    PLANNED = "planned"
    OFFLINE = "offline"
    DECOMMISSIONED = "decommissioned"


class InterfaceType(StrEnum):
    COPPER = "copper"
    FIBER = "fiber"
    WIRELESS = "wireless"
    VIRTUAL = "virtual"   # SVI / VLAN interface / loopback
    LAG = "lag"           # port-channel / trunk aggregato
    OTHER = "other"


class InterfaceMode(StrEnum):
    ACCESS = "access"
    TRUNK = "trunk"


class CableType(StrEnum):
    CAT5E = "cat5e"
    CAT6 = "cat6"
    CAT6A = "cat6a"
    FIBER_SM = "fiber_sm"
    FIBER_MM = "fiber_mm"
    DAC = "dac"
    OTHER = "other"


class CableStatus(StrEnum):
    CONNECTED = "connected"
    PLANNED = "planned"
    DECOMMISSIONING = "decommissioning"


class IPAMStatus(StrEnum):
    ACTIVE = "active"
    RESERVED = "reserved"
    DEPRECATED = "deprecated"


class IPAddressStatus(StrEnum):
    ACTIVE = "active"
    RESERVED = "reserved"
    DHCP = "dhcp"
    DEPRECATED = "deprecated"


# Interfacce che non possono avere un cavo fisico
NON_CABLEABLE_TYPES = {InterfaceType.VIRTUAL.value, InterfaceType.LAG.value}
