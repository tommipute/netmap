"""Abbinamento tra quello che legge la scansione e quello che c'è nel database."""
import ipaddress
import re

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models import Device, Interface, IPAddress
from app.models.enums import InterfaceType

# Nomi lunghi -> abbreviazioni, così "GigabitEthernet1/0/1" e "Gi1/0/1" sono la stessa porta
_IF_PREFIXES = [
    ("hundredgigabitethernet", "hu"),
    ("hundredgige", "hu"),
    ("fortygigabitethernet", "fo"),
    ("twentyfivegigabitethernet", "twe"),
    ("twentyfivegige", "twe"),
    ("tengigabitethernet", "te"),
    ("tengige", "te"),
    ("fivegigabitethernet", "fi"),
    ("twogigabitethernet", "tw"),
    ("gigabitethernet", "gi"),
    ("fastethernet", "fa"),
    ("ethernet", "eth"),
    ("port-channel", "po"),
    ("portchannel", "po"),
    ("management", "mgmt"),
    ("loopback", "lo"),
    ("vlan", "vl"),
]

# ifType IANA -> tipo di interfaccia. Ethernet resta "copper": rame o fibra via SNMP non si distingue
_IF_TYPES = {
    6: InterfaceType.COPPER.value,      # ethernetCsmacd
    117: InterfaceType.COPPER.value,    # gigabitEthernet
    62: InterfaceType.COPPER.value,     # fastEther
    71: InterfaceType.WIRELESS.value,   # ieee80211
    161: InterfaceType.LAG.value,       # ieee8023adLag
    24: InterfaceType.VIRTUAL.value,    # softwareLoopback
    53: InterfaceType.VIRTUAL.value,    # propVirtual
    131: InterfaceType.VIRTUAL.value,   # tunnel
    135: InterfaceType.VIRTUAL.value,   # l2vlan
    136: InterfaceType.VIRTUAL.value,   # l3ipvlan
}


def norm_ifname(name: str | None) -> str:
    if not name:
        return ""
    text = re.sub(r"\s+", "", name.lower())
    for long, short in _IF_PREFIXES:
        if text.startswith(long):
            return short + text[len(long):]
    return text


def interface_type(if_type: int | None) -> str:
    return _IF_TYPES.get(if_type, InterfaceType.OTHER.value) if if_type is not None else InterfaceType.OTHER.value


def short_name(sys_name: str | None) -> str | None:
    """'SW-CORE-01.corp.local' -> 'sw-core-01' (un IP resta com'è)."""
    if not sys_name:
        return None
    text = sys_name.strip().lower()
    try:
        ipaddress.ip_address(text)
        return text
    except ValueError:
        return text.split(".", 1)[0] or None


def find_device(
    db: Session,
    *,
    serial: str | None = None,
    sys_name: str | None = None,
    ips: list[str] | None = None,
    macs: list[str] | None = None,
) -> Device | None:
    """Device già noto: numero di serie -> sysName (senza dominio) -> IP registrato -> MAC di una porta."""
    if serial:
        device = db.scalars(select(Device).where(func.lower(Device.serial) == serial.lower())).first()
        if device:
            return device

    short = short_name(sys_name)
    if short:
        candidates = db.scalars(
            select(Device).where(
                or_(
                    func.lower(Device.name) == short,
                    func.lower(Device.sys_name) == sys_name.strip().lower(),
                    func.lower(Device.sys_name) == short,
                    func.lower(Device.sys_name).like(f"{short}.%"),
                )
            ).order_by(Device.id)
        ).all()
        if candidates:
            return candidates[0]

    hosts = [str(ipaddress.ip_interface(ip).ip) for ip in ips or [] if ip]
    if hosts:
        ip = db.scalars(
            select(IPAddress).where(IPAddress.host.in_(hosts), IPAddress.interface_id.is_not(None)).order_by(IPAddress.id)
        ).first()
        if ip:
            return ip.interface.device

    macs = [m for m in macs or [] if m]
    if macs:
        iface = db.scalars(select(Interface).where(Interface.mac_address.in_(macs)).order_by(Interface.id)).first()
        if iface:
            return iface.device
    return None


def find_port(interfaces: list[Interface], *, names: list[str | None] = (), mac: str | None = None,
              if_index: int | None = None) -> Interface | None:
    if mac:
        for iface in interfaces:
            if iface.mac_address == mac:
                return iface
    wanted = [norm_ifname(n) for n in names if n]
    for key in wanted:
        for iface in interfaces:
            if norm_ifname(iface.name) == key:
                return iface
    if if_index is not None:
        for iface in interfaces:
            if iface.if_index == if_index:
                return iface
    return None
