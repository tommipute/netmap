"""Lettura SNMP dei device con pysnmp 7 (API asyncio). Non tocca il database.

Per ogni host si provano i profili nell'ordine del job: il primo che risponde al `get` di sistema
viene usato per leggere il resto (interfacce, IP, seriale, vicini LLDP/CDP).
"""
import asyncio
import ipaddress
import logging
import re
from dataclasses import dataclass, field
from typing import Any

from pysnmp.hlapi.v3arch.asyncio import (
    USM_AUTH_HMAC96_MD5,
    USM_AUTH_HMAC96_SHA,
    USM_AUTH_HMAC192_SHA256,
    USM_AUTH_HMAC384_SHA512,
    USM_AUTH_NONE,
    USM_PRIV_CBC56_DES,
    USM_PRIV_CFB128_AES,
    USM_PRIV_CFB256_AES,
    USM_PRIV_NONE,
    CommunityData,
    ContextData,
    ObjectIdentity,
    ObjectType,
    SnmpEngine,
    UdpTransportTarget,
    UsmUserData,
    bulk_walk_cmd,
    get_cmd,
)

from app.core.net import normalize_mac

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------- OID
SYS_DESCR = "1.3.6.1.2.1.1.1.0"
SYS_OBJECT_ID = "1.3.6.1.2.1.1.2.0"
SYS_NAME = "1.3.6.1.2.1.1.5.0"
SYS_LOCATION = "1.3.6.1.2.1.1.6.0"

IF_DESCR = "1.3.6.1.2.1.2.2.1.2"
IF_TYPE = "1.3.6.1.2.1.2.2.1.3"
IF_MTU = "1.3.6.1.2.1.2.2.1.4"
IF_SPEED = "1.3.6.1.2.1.2.2.1.5"
IF_PHYS_ADDRESS = "1.3.6.1.2.1.2.2.1.6"
IF_ADMIN_STATUS = "1.3.6.1.2.1.2.2.1.7"
IF_OPER_STATUS = "1.3.6.1.2.1.2.2.1.8"
IF_NAME = "1.3.6.1.2.1.31.1.1.1.1"
IF_HIGH_SPEED = "1.3.6.1.2.1.31.1.1.1.15"
IF_ALIAS = "1.3.6.1.2.1.31.1.1.1.18"

IP_AD_IF_INDEX = "1.3.6.1.2.1.4.20.1.2"      # ipAddrTable (IPv4), indice = indirizzo
IP_AD_NET_MASK = "1.3.6.1.2.1.4.20.1.3"
IP_ADDRESS_IF_INDEX = "1.3.6.1.2.1.4.34.1.3"  # ipAddressTable (IPv4 e IPv6), indice = tipo.lunghezza.indirizzo
IP_ADDRESS_PREFIX = "1.3.6.1.2.1.4.34.1.5"    # puntatore al prefisso: l'ultimo numero è la lunghezza

ENT_PHYSICAL_PARENT_REL_POS = "1.3.6.1.2.1.47.1.1.1.1.6"  # per gli chassis di uno stack: numero del membro
ENT_PHYSICAL_CLASS = "1.3.6.1.2.1.47.1.1.1.1.5"
ENT_PHYSICAL_SERIAL = "1.3.6.1.2.1.47.1.1.1.1.11"
ENT_PHYSICAL_MODEL = "1.3.6.1.2.1.47.1.1.1.1.13"
ENT_CLASS_CHASSIS = 3

LLDP_LOC_PORT_ID_SUBTYPE = "1.0.8802.1.1.2.1.3.7.1.2"
LLDP_LOC_PORT_ID = "1.0.8802.1.1.2.1.3.7.1.3"
LLDP_LOC_PORT_DESC = "1.0.8802.1.1.2.1.3.7.1.4"
LLDP_REM_CHASSIS_ID_SUBTYPE = "1.0.8802.1.1.2.1.4.1.1.4"   # indice: timeMark.porta locale.indice remoto
LLDP_REM_CHASSIS_ID = "1.0.8802.1.1.2.1.4.1.1.5"
LLDP_REM_PORT_ID_SUBTYPE = "1.0.8802.1.1.2.1.4.1.1.6"
LLDP_REM_PORT_ID = "1.0.8802.1.1.2.1.4.1.1.7"
LLDP_REM_PORT_DESC = "1.0.8802.1.1.2.1.4.1.1.8"
LLDP_REM_SYS_NAME = "1.0.8802.1.1.2.1.4.1.1.9"
LLDP_REM_MAN_ADDR_IF_SUBTYPE = "1.0.8802.1.1.2.1.4.2.1.3"  # l'indirizzo di management sta nell'indice

CDP_CACHE_ADDRESS_TYPE = "1.3.6.1.4.1.9.9.23.1.2.1.1.3"    # indice: ifIndex locale.indice
CDP_CACHE_ADDRESS = "1.3.6.1.4.1.9.9.23.1.2.1.1.4"
CDP_CACHE_DEVICE_ID = "1.3.6.1.4.1.9.9.23.1.2.1.1.6"
CDP_CACHE_DEVICE_PORT = "1.3.6.1.4.1.9.9.23.1.2.1.1.7"

# Tabelle MAC (BRIDGE-MIB, Q-BRIDGE-MIB), VLAN e ARP: servono a "dov'è collegato?"
DOT1D_BASE_PORT_IF_INDEX = "1.3.6.1.2.1.17.1.4.1.2"   # porta bridge -> ifIndex
DOT1D_TP_FDB_PORT = "1.3.6.1.2.1.17.4.3.1.2"          # indice: MAC (6 numeri)
DOT1D_TP_FDB_STATUS = "1.3.6.1.2.1.17.4.3.1.3"
DOT1Q_TP_FDB_PORT = "1.3.6.1.2.1.17.7.1.2.2.1.2"      # indice: fdbId (di solito = VLAN) . MAC
DOT1Q_TP_FDB_STATUS = "1.3.6.1.2.1.17.7.1.2.2.1.3"
DOT1Q_PVID = "1.3.6.1.2.1.17.7.1.4.5.1.1"             # VLAN untagged della porta bridge
DOT1Q_VLAN_STATIC_NAME = "1.3.6.1.2.1.17.7.1.4.3.1.1" # indice: VID
DOT1Q_VLAN_STATIC_EGRESS = "1.3.6.1.2.1.17.7.1.4.3.1.2"    # indice: VID, valore: bitmap delle porte bridge
DOT1Q_VLAN_STATIC_UNTAGGED = "1.3.6.1.2.1.17.7.1.4.3.1.4"  # porte dove la VLAN esce senza tag
# I Cisco non usano Q-BRIDGE per le VLAN delle porte: CISCO-VLAN-MEMBERSHIP-MIB e CISCO-VTP-MIB
CISCO_VM_VLAN = "1.3.6.1.4.1.9.9.68.1.2.2.1.2"         # VLAN di una porta access, indice: ifIndex
CISCO_TRUNK_ENABLED = "1.3.6.1.4.1.9.9.46.1.6.1.1.4"   # bitmap delle VLAN 0-1023 permesse sul trunk
CISCO_TRUNK_NATIVE = "1.3.6.1.4.1.9.9.46.1.6.1.1.5"
CISCO_TRUNK_STATUS = "1.3.6.1.4.1.9.9.46.1.6.1.1.14"   # 1 = la porta è in trunk
CISCO_VTP_VLAN_NAME = "1.3.6.1.4.1.9.9.46.1.3.1.1.4"   # indice: dominio VTP . VID
CISCO_TRUNKING = 1
CISCO_RESERVED_VLANS = range(1002, 1006)               # fddi/token ring di default, sempre presenti
IP_NET_TO_MEDIA_PHYS = "1.3.6.1.2.1.4.22.1.2"         # ARP IPv4, indice: ifIndex . indirizzo
IP_NET_TO_MEDIA_TYPE = "1.3.6.1.2.1.4.22.1.4"
IP_NET_TO_PHYSICAL_PHYS = "1.3.6.1.2.1.4.35.1.4"      # ARP/ND, indice: ifIndex . tipo . lunghezza . indirizzo
FDB_LEARNED = 3
FDB_SELF = 4
ARP_INVALID = 2

# LldpChassisIdSubtype / LldpPortIdSubtype
LLDP_CHASSIS_MAC = 4
LLDP_CHASSIS_NETWORK_ADDRESS = 5
LLDP_PORT_ALIAS = 1
LLDP_PORT_MAC = 3
LLDP_PORT_NAME = 5
LLDP_PORT_LOCAL = 7

OPER_STATUS = {1: "up", 2: "down", 3: "testing", 4: "unknown", 5: "dormant", 6: "absent", 7: "down"}

AUTH_PROTOCOLS = {
    None: USM_AUTH_NONE,
    "md5": USM_AUTH_HMAC96_MD5,
    "sha": USM_AUTH_HMAC96_SHA,
    "sha256": USM_AUTH_HMAC192_SHA256,
    "sha512": USM_AUTH_HMAC384_SHA512,
}
PRIV_PROTOCOLS = {
    None: USM_PRIV_NONE,
    "des": USM_PRIV_CBC56_DES,
    "aes": USM_PRIV_CFB128_AES,
    "aes256": USM_PRIV_CFB256_AES,
}


# ---------------------------------------------------------------- dati letti
@dataclass
class Credentials:
    profile_id: int
    name: str
    version: str = "v2c"
    port: int = 161
    timeout: float = 2.0
    retries: int = 1
    community: str | None = None
    username: str | None = None
    auth_protocol: str | None = None
    auth_key: str | None = None
    priv_protocol: str | None = None
    priv_key: str | None = None
    context: str | None = None  # SNMPv3: context name, quasi sempre vuoto


@dataclass
class IfData:
    if_index: int
    name: str
    descr: str | None = None
    alias: str | None = None
    if_type: int | None = None
    mtu: int | None = None
    speed_mbps: int | None = None
    mac: str | None = None
    admin_up: bool | None = None
    oper_status: str | None = None


@dataclass
class IpData:
    address: str  # con maschera: 10.0.0.1/24
    if_index: int | None = None


@dataclass
class NeighborData:
    protocol: str                      # lldp / cdp
    local_if_index: int | None
    sys_name: str | None = None
    chassis_mac: str | None = None
    port_id: str | None = None
    port_id_type: str = "name"         # name / mac / local
    port_descr: str | None = None
    addresses: list[str] = field(default_factory=list)  # IP di management del vicino


@dataclass
class FdbEntry:
    """Riga della tabella MAC di uno switch: quel MAC è stato visto su quella porta."""
    mac: str
    if_index: int
    vlan: int | None = None


@dataclass
class ArpEntry:
    ip: str
    mac: str
    if_index: int | None = None


@dataclass
class MemberData:
    """Un membro di uno stack (uno chassis della ENTITY-MIB)."""

    number: int
    serial: str | None = None
    model: str | None = None


@dataclass
class HostData:
    host: str
    profile_id: int | None = None
    profile_name: str | None = None
    sys_name: str | None = None
    sys_descr: str | None = None
    sys_object_id: str | None = None
    sys_location: str | None = None
    serial: str | None = None
    model: str | None = None
    interfaces: list[IfData] = field(default_factory=list)
    ips: list[IpData] = field(default_factory=list)
    neighbors: list[NeighborData] = field(default_factory=list)
    fdb: list[FdbEntry] = field(default_factory=list)
    arp: list[ArpEntry] = field(default_factory=list)
    vlans: dict[int, str] = field(default_factory=dict)       # VID -> nome
    port_vlans: dict[int, int] = field(default_factory=dict)  # ifIndex -> VLAN untagged (PVID / access / nativa)
    port_tagged: dict[int, list[int]] = field(default_factory=dict)  # ifIndex -> VLAN tagged (trunk)
    members: list[MemberData] = field(default_factory=list)  # stack: un elemento per switch (vuoto se non è uno stack)


# ---------------------------------------------------------------- conversioni
def _py(value: Any) -> Any:
    """Valore pysnmp -> tipo Python (bytes per le stringhe, così i MAC restano leggibili)."""
    kind = value.__class__.__name__
    if kind in ("NoSuchObject", "NoSuchInstance", "EndOfMibView", "Null"):
        return None
    if kind in ("OctetString", "Opaque", "Bits"):
        return bytes(value.asOctets())
    if kind in ("ObjectIdentifier", "ObjectName"):
        return str(value)
    if kind == "IpAddress":
        return str(ipaddress.IPv4Address(bytes(value.asOctets())))
    try:
        return int(value)
    except (TypeError, ValueError):
        return value.prettyPrint()


def _text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="replace")
    text = str(value).replace("\x00", "").strip()
    return text or None


def _mac(value: Any) -> str | None:
    if isinstance(value, bytes) and len(value) == 6:
        return ":".join(f"{b:02X}" for b in value)
    text = _text(value)
    if not text:
        return None
    try:
        return normalize_mac(text)
    except ValueError:
        return None


def _int(value: Any) -> int | None:
    return value if isinstance(value, int) else None


def _ip_from_bytes(raw: bytes | list[int] | tuple[int, ...]) -> str | None:
    raw = bytes(raw)
    try:
        if len(raw) == 4:
            return str(ipaddress.IPv4Address(raw))
        if len(raw) == 16:
            return str(ipaddress.IPv6Address(raw))
    except ValueError:
        return None
    return None


def _useful_ip(address: str) -> bool:
    ip = ipaddress.ip_interface(address).ip
    return not (ip.is_loopback or ip.is_link_local or ip.is_unspecified or ip.is_multicast)


_CDP_SERIAL_SUFFIX = re.compile(r"\([^)]*\)$")  # Nexus: "switch(FOX1234)"


# ---------------------------------------------------------------- SNMP a basso livello
def _auth_data(creds: Credentials):
    if creds.version == "v3":
        return UsmUserData(
            creds.username or "",
            authKey=creds.auth_key or None,
            privKey=creds.priv_key or None,
            authProtocol=AUTH_PROTOCOLS.get(creds.auth_protocol, USM_AUTH_NONE),
            privProtocol=PRIV_PROTOCOLS.get(creds.priv_protocol, USM_PRIV_NONE),
        )
    return CommunityData(creds.community or "", mpModel=1)  # mpModel=1 -> SNMP v2c


class _Session:
    def __init__(self, engine: SnmpEngine, host: str, creds: Credentials, transport):
        self.engine, self.host, self.creds, self.transport = engine, host, creds, transport
        self.auth = _auth_data(creds)
        self.context = ContextData(contextName=creds.context or "")

    async def get(self, *oids: str) -> dict[str, Any] | None:
        error, status, _index, var_binds = await get_cmd(
            self.engine, self.auth, self.transport, self.context,
            *(ObjectType(ObjectIdentity(oid)) for oid in oids),
            lookupMib=False,
        )
        if error or status:
            return None
        return {str(vb[0]): _py(vb[1]) for vb in var_binds}

    async def walk(self, oid: str) -> dict[tuple[int, ...], Any]:
        """Colonna di una tabella: {indice (tupla dopo l'OID della colonna): valore}."""
        prefix = tuple(int(part) for part in oid.split("."))
        result: dict[tuple[int, ...], Any] = {}
        async for error, status, _index, var_binds in bulk_walk_cmd(
            self.engine, self.auth, self.transport, self.context, 0, 25,
            ObjectType(ObjectIdentity(oid)),
            lexicographicMode=False, lookupMib=False,
        ):
            if error or status:
                logger.debug("%s: walk %s interrotto (%s)", self.host, oid, error or status.prettyPrint())
                break
            for vb in var_binds:
                name = tuple(vb[0])
                if name[: len(prefix)] != prefix:
                    continue
                value = _py(vb[1])
                if value is not None:
                    result[name[len(prefix):]] = value
        return result


# ---------------------------------------------------------------- lettura di un host
async def _interfaces(s: _Session) -> list[IfData]:
    descr = await s.walk(IF_DESCR)
    columns = {
        oid: await s.walk(oid)
        for oid in (IF_NAME, IF_TYPE, IF_MTU, IF_SPEED, IF_HIGH_SPEED, IF_PHYS_ADDRESS, IF_ADMIN_STATUS, IF_OPER_STATUS, IF_ALIAS)
    }
    result = []
    for index in sorted(set(descr) | set(columns[IF_NAME])):
        if len(index) != 1:
            continue
        if_index = index[0]
        name = _text(columns[IF_NAME].get(index)) or _text(descr.get(index))
        if not name:
            continue
        high_speed = _int(columns[IF_HIGH_SPEED].get(index))
        speed = _int(columns[IF_SPEED].get(index))
        speed_mbps = high_speed if high_speed else (speed // 1_000_000 if speed else None)
        admin = _int(columns[IF_ADMIN_STATUS].get(index))
        result.append(IfData(
            if_index=if_index,
            name=name[:100],
            descr=_text(descr.get(index)),
            alias=_text(columns[IF_ALIAS].get(index)),
            if_type=_int(columns[IF_TYPE].get(index)),
            mtu=_int(columns[IF_MTU].get(index)) or None,
            speed_mbps=speed_mbps or None,
            mac=_mac(columns[IF_PHYS_ADDRESS].get(index)),
            admin_up={1: True, 2: False}.get(admin),
            oper_status=OPER_STATUS.get(_int(columns[IF_OPER_STATUS].get(index))),
        ))
    return result


async def _ips(s: _Session) -> list[IpData]:
    result: dict[str, IpData] = {}
    if_index = await s.walk(IP_AD_IF_INDEX)
    masks = await s.walk(IP_AD_NET_MASK)
    for index, value in if_index.items():
        if len(index) != 4:
            continue
        host = ".".join(str(n) for n in index)
        mask = masks.get(index)
        prefixlen = ipaddress.IPv4Network(f"0.0.0.0/{mask}").prefixlen if isinstance(mask, str) else 32
        result[host] = IpData(address=f"{host}/{prefixlen}", if_index=_int(value))

    # ipAddressTable: unica fonte per gli IPv6 e per gli apparati senza ipAddrTable
    new_if_index = await s.walk(IP_ADDRESS_IF_INDEX)
    prefixes = await s.walk(IP_ADDRESS_PREFIX) if new_if_index else {}
    for index, value in new_if_index.items():
        if len(index) < 2 or index[1] != len(index) - 2:
            continue
        host = _ip_from_bytes(index[2:])
        if host is None or host in result:
            continue
        pointer = prefixes.get(index)
        last = pointer.rsplit(".", 1)[-1] if isinstance(pointer, str) else ""
        max_len = 32 if ":" not in host else 128
        prefixlen = int(last) if last.isdigit() and 0 < int(last) <= max_len else max_len
        result[host] = IpData(address=f"{host}/{prefixlen}", if_index=_int(value))

    return [ip for ip in result.values() if _useful_ip(ip.address)]


async def _chassis(s: _Session) -> tuple[str | None, str | None, list[MemberData]]:
    """Seriale e modello del device (primo chassis) e, se gli chassis sono più di uno, i membri dello stack.

    Il numero del membro è entPhysicalParentRelPos (negli stack Cisco lo chassis sta nel contenitore dello stack
    alla posizione del membro); se manca, l'ordine degli chassis.
    """
    classes = await s.walk(ENT_PHYSICAL_CLASS)
    chassis = sorted(index for index, value in classes.items() if value == ENT_CLASS_CHASSIS)
    if not chassis:
        return None, None, []
    serials = await s.walk(ENT_PHYSICAL_SERIAL)
    models = await s.walk(ENT_PHYSICAL_MODEL)
    found = [(index, _text(serials.get(index)), _text(models.get(index))) for index in chassis]
    found = [c for c in found if c[1] or c[2]]
    if not found:
        return None, None, []
    members: list[MemberData] = []
    if len(found) > 1:
        positions = await s.walk(ENT_PHYSICAL_PARENT_REL_POS)
        numbers = [_int(positions.get(index)) for index, _s, _m in found]
        if len(set(numbers)) != len(numbers) or any(not n or n < 1 for n in numbers):
            numbers = list(range(1, len(found) + 1))
        members = sorted((MemberData(number=n, serial=serial, model=model)
                          for n, (_i, serial, model) in zip(numbers, found)), key=lambda m: m.number)
    return found[0][1], found[0][2], members


def _name_key(name: str) -> str:
    return re.sub(r"\s+", "", name.lower())


def _lldp_local_ports(interfaces: list[IfData], subtypes: dict, ids: dict, descs: dict) -> dict[int, int]:
    """lldpLocPortNum -> ifIndex. Spesso coincidono, ma non sempre: si confrontano nome e MAC."""
    by_name: dict[str, int] = {}
    for i in interfaces:
        for name in (i.name, i.descr):
            if name:
                by_name.setdefault(_name_key(name), i.if_index)
    by_mac = {i.mac: i.if_index for i in interfaces if i.mac}
    if_indexes = {i.if_index for i in interfaces}

    result = {}
    for index in set(subtypes) | set(ids) | set(descs):
        port_num = index[0]
        found = None
        if subtypes.get(index) == LLDP_PORT_MAC:
            found = by_mac.get(_mac(ids.get(index)))
        if found is None:
            for candidate in (ids.get(index), descs.get(index)):
                text = _text(candidate)
                if text and _name_key(text) in by_name:
                    found = by_name[_name_key(text)]
                    break
        if found is None and port_num in if_indexes:
            found = port_num
        if found is not None:
            result[port_num] = found
    return result


async def _lldp(s: _Session, interfaces: list[IfData]) -> list[NeighborData]:
    chassis_ids = await s.walk(LLDP_REM_CHASSIS_ID)
    if not chassis_ids:
        return []
    chassis_types = await s.walk(LLDP_REM_CHASSIS_ID_SUBTYPE)
    port_types = await s.walk(LLDP_REM_PORT_ID_SUBTYPE)
    port_ids = await s.walk(LLDP_REM_PORT_ID)
    port_descs = await s.walk(LLDP_REM_PORT_DESC)
    sys_names = await s.walk(LLDP_REM_SYS_NAME)
    man_addrs = await s.walk(LLDP_REM_MAN_ADDR_IF_SUBTYPE)
    local_ports = _lldp_local_ports(
        interfaces,
        await s.walk(LLDP_LOC_PORT_ID_SUBTYPE),
        await s.walk(LLDP_LOC_PORT_ID),
        await s.walk(LLDP_LOC_PORT_DESC),
    )

    addresses: dict[tuple, list[str]] = {}
    for index in man_addrs:
        # timeMark.porta.indice . tipo indirizzo . lunghezza . byte dell'indirizzo
        if len(index) > 5 and index[4] == len(index) - 5:
            address = _ip_from_bytes(index[5:])
            if address:
                addresses.setdefault(index[:3], []).append(address)

    result = []
    for index, chassis_raw in chassis_ids.items():
        if len(index) != 3:
            continue
        neighbor = NeighborData(protocol="lldp", local_if_index=local_ports.get(index[1]))
        chassis_type = chassis_types.get(index)
        if chassis_type == LLDP_CHASSIS_MAC:
            neighbor.chassis_mac = _mac(chassis_raw)
        elif chassis_type == LLDP_CHASSIS_NETWORK_ADDRESS and isinstance(chassis_raw, bytes) and len(chassis_raw) > 1:
            address = _ip_from_bytes(chassis_raw[1:])  # primo byte: famiglia (1 = IPv4)
            if address:
                neighbor.addresses.append(address)
        port_type, port_raw = port_types.get(index), port_ids.get(index)
        if port_type == LLDP_PORT_MAC:
            neighbor.port_id, neighbor.port_id_type = _mac(port_raw), "mac"
        else:
            neighbor.port_id = _text(port_raw)
            neighbor.port_id_type = "local" if port_type == LLDP_PORT_LOCAL else "name"
        neighbor.port_descr = _text(port_descs.get(index))
        neighbor.sys_name = _text(sys_names.get(index))
        neighbor.addresses += addresses.get(index, [])
        result.append(neighbor)
    return result


async def _cdp(s: _Session) -> list[NeighborData]:
    device_ids = await s.walk(CDP_CACHE_DEVICE_ID)
    if not device_ids:
        return []
    ports = await s.walk(CDP_CACHE_DEVICE_PORT)
    address_types = await s.walk(CDP_CACHE_ADDRESS_TYPE)
    raw_addresses = await s.walk(CDP_CACHE_ADDRESS)
    result = []
    for index, raw in device_ids.items():
        if len(index) != 2:
            continue
        name = _text(raw)
        neighbor = NeighborData(
            protocol="cdp",
            local_if_index=index[0],
            sys_name=_CDP_SERIAL_SUFFIX.sub("", name) if name else None,
            port_id=_text(ports.get(index)),
        )
        address = raw_addresses.get(index)
        if address_types.get(index) == 1 and isinstance(address, bytes):  # 1 = IP
            ip = _ip_from_bytes(address)
            if ip:
                neighbor.addresses.append(ip)
        result.append(neighbor)
    return result


def _mac_from_index(index: tuple[int, ...]) -> str | None:
    if len(index) != 6 or any(not 0 <= b <= 255 for b in index):
        return None
    return ":".join(f"{b:02X}" for b in index)


def bitmap_positions(raw: Any) -> list[int]:
    """Posizioni (da 1) dei bit accesi in una bitmap SNMP (PortList): il primo bit è il più significativo."""
    if not isinstance(raw, bytes):
        return []
    return [i * 8 + bit + 1 for i, byte in enumerate(raw) for bit in range(8) if byte & (0x80 >> bit)]


async def _base_ports(s: _Session) -> dict[int, int]:
    """Porta bridge -> ifIndex"""
    return {index[0]: value for index, value in (await s.walk(DOT1D_BASE_PORT_IF_INDEX)).items()
            if len(index) == 1 and isinstance(value, int)}


async def _bridge(s: _Session, base_ports: dict[int, int], port_vlans: dict[int, int]) -> tuple[list[FdbEntry], dict[int, int]]:
    """Tabella MAC: prima Q-BRIDGE (con la VLAN), altrimenti BRIDGE-MIB (VLAN presa da port_vlans, es. Cisco).
    Ritorna anche il PVID delle porte."""
    if not base_ports:
        return [], {}
    pvids = {base_ports[index[0]]: value for index, value in (await s.walk(DOT1Q_PVID)).items()
             if len(index) == 1 and index[0] in base_ports and isinstance(value, int)}

    entries: dict[tuple[str, int, int | None], FdbEntry] = {}

    def add(mac: str | None, base_port: Any, status: Any, vlan: int | None) -> None:
        if_index = base_ports.get(base_port) if isinstance(base_port, int) else None
        if mac is None or if_index is None or (status is not None and status != FDB_LEARNED):
            return
        entries.setdefault((mac, if_index, vlan), FdbEntry(mac=mac, if_index=if_index, vlan=vlan))

    q_ports = await s.walk(DOT1Q_TP_FDB_PORT)
    if q_ports:
        q_status = await s.walk(DOT1Q_TP_FDB_STATUS)
        for index, port in q_ports.items():
            if len(index) == 7:
                add(_mac_from_index(index[1:]), port, q_status.get(index), index[0])
    else:
        ports = await s.walk(DOT1D_TP_FDB_PORT)
        status = await s.walk(DOT1D_TP_FDB_STATUS) if ports else {}
        for index, port in ports.items():
            mac = _mac_from_index(index)
            if_index = base_ports.get(port) if isinstance(port, int) else None
            add(mac, port, status.get(index), pvids.get(if_index, port_vlans.get(if_index)))
    return sorted(entries.values(), key=lambda e: (e.mac, e.if_index, e.vlan or 0)), pvids


async def _qbridge_tagged(s: _Session, base_ports: dict[int, int]) -> dict[int, list[int]]:
    """VLAN tagged di ogni porta da Q-BRIDGE: porte in cui la VLAN esce, meno quelle dove esce senza tag."""
    egress = await s.walk(DOT1Q_VLAN_STATIC_EGRESS)
    if not egress:
        return {}
    untagged = await s.walk(DOT1Q_VLAN_STATIC_UNTAGGED)
    tagged: dict[int, list[int]] = {}
    for index, raw in egress.items():
        if len(index) != 1:
            continue
        for port in set(bitmap_positions(raw)) - set(bitmap_positions(untagged.get(index))):
            if port in base_ports:
                tagged.setdefault(base_ports[port], []).append(index[0])
    return {if_index: sorted(vids) for if_index, vids in tagged.items()}


async def _cisco_vlans(s: _Session) -> tuple[dict[int, str], dict[int, int], dict[int, list[int]]]:
    """Nomi delle VLAN (VTP), VLAN untagged (access o nativa del trunk) e VLAN tagged dei trunk."""
    names = {index[1]: _text(value) or str(index[1]) for index, value in (await s.walk(CISCO_VTP_VLAN_NAME)).items()
             if len(index) == 2 and index[1] not in CISCO_RESERVED_VLANS}
    untagged = {index[0]: value for index, value in (await s.walk(CISCO_VM_VLAN)).items()
                if len(index) == 1 and isinstance(value, int)}
    tagged: dict[int, list[int]] = {}
    trunks = [index[0] for index, value in (await s.walk(CISCO_TRUNK_STATUS)).items()
              if len(index) == 1 and value == CISCO_TRUNKING]
    if trunks:
        native = await s.walk(CISCO_TRUNK_NATIVE)
        enabled = await s.walk(CISCO_TRUNK_ENABLED)
        for if_index in trunks:
            native_vid = native.get((if_index,))
            if isinstance(native_vid, int):
                untagged[if_index] = native_vid
            # Spesso il trunk "permette tutto" (1-4094): contano solo le VLAN che esistono sullo switch
            allowed = [p - 1 for p in bitmap_positions(enabled.get((if_index,)))]
            tagged[if_index] = sorted(v for v in allowed if v in names and v != native_vid)
    return names, untagged, tagged


async def _vlan_names(s: _Session) -> dict[int, str]:
    names = await s.walk(DOT1Q_VLAN_STATIC_NAME)
    return {index[0]: _text(value) or str(index[0]) for index, value in names.items() if len(index) == 1}


async def _arp(s: _Session) -> list[ArpEntry]:
    result: dict[str, ArpEntry] = {}
    types = await s.walk(IP_NET_TO_MEDIA_TYPE)
    for index, raw in (await s.walk(IP_NET_TO_MEDIA_PHYS)).items():
        if len(index) != 5 or types.get(index) == ARP_INVALID:
            continue
        mac, ip = _mac(raw), ".".join(str(n) for n in index[1:])
        if mac and mac != "00:00:00:00:00:00":
            result[ip] = ArpEntry(ip=ip, mac=mac, if_index=index[0])
    if not result:
        for index, raw in (await s.walk(IP_NET_TO_PHYSICAL_PHYS)).items():
            if len(index) < 4 or index[2] != len(index) - 3:
                continue
            ip, mac = _ip_from_bytes(index[3:]), _mac(raw)
            if ip and mac and mac != "00:00:00:00:00:00" and _useful_ip(ip):
                result.setdefault(ip, ArpEntry(ip=ip, mac=mac, if_index=index[0]))
    return sorted(result.values(), key=lambda a: ipaddress.ip_address(a.ip))


async def _read_host(s: _Session, system: dict[str, Any]) -> HostData:
    data = HostData(
        host=s.host,
        profile_id=s.creds.profile_id,
        profile_name=s.creds.name,
        sys_name=_text(system.get(SYS_NAME)),
        sys_descr=_text(system.get(SYS_DESCR)),
        sys_object_id=_text(system.get(SYS_OBJECT_ID)),
        sys_location=_text(system.get(SYS_LOCATION)),
    )
    data.interfaces = await _interfaces(s)
    data.ips = await _ips(s)
    data.serial, data.model, data.members = await _chassis(s)
    data.neighbors = await _lldp(s, data.interfaces) + await _cdp(s)
    cisco_names, cisco_untagged, cisco_tagged = await _cisco_vlans(s)
    base_ports = await _base_ports(s)
    data.fdb, pvids = await _bridge(s, base_ports, cisco_untagged)
    data.port_vlans = {**cisco_untagged, **pvids}
    data.port_tagged = {**cisco_tagged, **await _qbridge_tagged(s, base_ports)}
    data.vlans = {**cisco_names, **await _vlan_names(s)}
    data.arp = await _arp(s)
    return data


async def collect_host(engine: SnmpEngine, host: str, credentials: list[Credentials]) -> HostData | None:
    """Prova i profili in ordine; None se nessuno risponde."""
    for creds in credentials:
        transport = await UdpTransportTarget.create((host, creds.port), timeout=creds.timeout, retries=creds.retries)
        session = _Session(engine, host, creds, transport)
        system = await session.get(SYS_NAME, SYS_DESCR, SYS_OBJECT_ID, SYS_LOCATION)
        if system is None:
            continue
        return await _read_host(session, system)
    return None


async def collect_all_async(hosts: list[str], credentials: list[Credentials], concurrency: int) -> list[HostData]:
    engine = SnmpEngine()
    semaphore = asyncio.Semaphore(concurrency)

    async def one(host: str) -> HostData | Exception | None:
        async with semaphore:
            try:
                return await collect_host(engine, host, credentials)
            except Exception as exc:  # un host problematico non deve fermare gli altri
                logger.warning("%s: lettura SNMP fallita: %s", host, exc)
                return exc

    try:
        results = await asyncio.gather(*(one(h) for h in hosts))
    finally:
        engine.close_dispatcher()
    return [r for r in results if isinstance(r, HostData)]


def collect_all(hosts: list[str], credentials: list[Credentials], concurrency: int = 50) -> list[HostData]:
    return asyncio.run(collect_all_async(hosts, credentials, concurrency))
