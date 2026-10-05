"""Funzioni di utilità per MAC address e indirizzi IP."""
import ipaddress
import re

_NOT_HEX = re.compile(r"[^0-9a-fA-F]")


def normalize_mac(value: str) -> str:
    """Accetta aa:bb:cc:dd:ee:ff, aa-bb-..., aabb.ccdd.eeff (Cisco) -> AA:BB:CC:DD:EE:FF."""
    hex_only = _NOT_HEX.sub("", value).upper()
    if len(hex_only) != 12:
        raise ValueError(f"MAC address non valido: {value}")
    return ":".join(hex_only[i:i + 2] for i in range(0, 12, 2))


def normalize_prefix(value: str) -> str:
    """'10.0.0.7/24' -> '10.0.0.0/24'."""
    try:
        return str(ipaddress.ip_network(value.strip(), strict=False))
    except ValueError as exc:
        raise ValueError(f"Prefisso non valido: {value}") from exc


def normalize_ip_interface(value: str) -> str:
    """'10.0.0.5/24' resta così, '10.0.0.5' diventa '10.0.0.5/32'."""
    try:
        return str(ipaddress.ip_interface(value.strip()))
    except ValueError as exc:
        raise ValueError(f"Indirizzo IP non valido: {value}") from exc


def ip_sort_key(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bytes:
    """Chiave binaria che ordina gli IP in modo corretto (10.0.0.2 prima di 10.0.0.10).

    IPv4 vengono prima degli IPv6. Funziona sia su Postgres che su SQLite.
    """
    return bytes([ip.version]) + ip.packed.rjust(16, b"\x00")


def prefix_sort_key(net: ipaddress.IPv4Network | ipaddress.IPv6Network) -> bytes:
    return ip_sort_key(net.network_address) + bytes([net.prefixlen])


def usable_host_count(net: ipaddress.IPv4Network | ipaddress.IPv6Network) -> int:
    """Host utilizzabili: esclude rete e broadcast per IPv4 fino a /30."""
    if net.version == 4 and net.prefixlen < 31:
        return net.num_addresses - 2
    return net.num_addresses
