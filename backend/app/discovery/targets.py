"""Intervalli da scansionare: '10.0.0.0/24', '10.0.0.5', '10.0.0.1-10.0.0.20' oppure '10.0.0.1-20'."""
import ipaddress
from collections.abc import Iterator

IPAddr = ipaddress.IPv4Address | ipaddress.IPv6Address


class TargetError(ValueError):
    pass


def _range(text: str) -> tuple[IPAddr, IPAddr]:
    first, last = (part.strip() for part in text.split("-", 1))
    try:
        start = ipaddress.ip_address(first)
        if start.version == 4 and last.isdigit():  # forma corta 10.0.0.1-20
            last = ".".join(first.split(".")[:3] + [last])
        end = ipaddress.ip_address(last)
    except ValueError as exc:
        raise TargetError(f"Intervallo non valido: {text}") from exc
    if start.version != end.version or end < start:
        raise TargetError(f"Intervallo non valido: {text}")
    return start, end


def normalize_target(text: str) -> str:
    """Controlla un intervallo e lo riscrive in forma standard."""
    text = text.strip()
    if not text:
        raise TargetError("Intervallo vuoto")
    if "-" in text:
        start, end = _range(text)
        return f"{start}-{end}"
    try:
        if "/" in text:
            return str(ipaddress.ip_network(text, strict=False))
        return str(ipaddress.ip_address(text))
    except ValueError as exc:
        raise TargetError(f"Indirizzo o subnet non valida: {text}") from exc


def count_hosts(target: str) -> int:
    if "-" in target:
        start, end = _range(target)
        return int(end) - int(start) + 1
    if "/" in target:
        net = ipaddress.ip_network(target, strict=False)
        return net.num_addresses - 2 if net.version == 4 and net.prefixlen < 31 else net.num_addresses
    return 1


def iter_hosts(target: str) -> Iterator[str]:
    if "-" in target:
        start, end = _range(target)
        for value in range(int(start), int(end) + 1):
            yield str(ipaddress.ip_address(value))
    elif "/" in target:
        net = ipaddress.ip_network(target, strict=False)
        hosts = net.hosts() if net.version == 4 and net.prefixlen < 31 else iter(net)
        for host in hosts:
            yield str(host)
    else:
        yield str(ipaddress.ip_address(target))


def validate_targets(targets: list[str], max_hosts: int) -> list[str]:
    normalized = [normalize_target(t) for t in targets]
    total = sum(count_hosts(t) for t in normalized)
    if total > max_hosts:
        raise TargetError(f"Troppi indirizzi da scansionare ({total}): il massimo è {max_hosts}")
    return normalized


def expand_targets(targets: list[str], max_hosts: int) -> list[str]:
    """Elenco di IP senza doppioni, nell'ordine in cui compaiono."""
    validate_targets(targets, max_hosts)
    seen: dict[str, None] = {}
    for target in targets:
        for host in iter_hosts(normalize_target(target)):
            seen.setdefault(host, None)
    return list(seen)
