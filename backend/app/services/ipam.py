import ipaddress

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.net import ip_sort_key, usable_host_count
from app.models import IPAddress, Prefix


def _ips_in_prefix(prefix: Prefix):
    """Condizione SQL: IP della stessa VRF che cadono dentro il prefisso (usa la sort_key binaria)."""
    net = ipaddress.ip_network(prefix.prefix)
    vrf = IPAddress.vrf_id.is_(None) if prefix.vrf_id is None else IPAddress.vrf_id == prefix.vrf_id
    in_range = IPAddress.sort_key.between(ip_sort_key(net.network_address), ip_sort_key(net.broadcast_address))
    return net, vrf & in_range


def prefix_utilization(db: Session, prefix: Prefix) -> dict:
    net, condition = _ips_in_prefix(prefix)
    used = db.scalar(select(func.count(IPAddress.id)).where(condition)) or 0
    total = usable_host_count(net)
    percent = round(min(used / total * 100, 100.0), 1) if total else 0.0
    return {"prefix": prefix.prefix, "total": total, "used": used, "percent": percent}


def prefix_ip_addresses(db: Session, prefix: Prefix, limit: int = 1024) -> list[IPAddress]:
    _, condition = _ips_in_prefix(prefix)
    return list(db.scalars(select(IPAddress).where(condition).order_by(IPAddress.sort_key).limit(limit)).unique())


def available_ips(db: Session, prefix: Prefix, limit: int) -> list[str]:
    net, condition = _ips_in_prefix(prefix)
    used = set(db.scalars(select(IPAddress.host).where(condition)))
    result: list[str] = []
    for host in net.hosts():
        if str(host) not in used:
            result.append(f"{host}/{net.prefixlen}")
            if len(result) >= limit:
                break
    return result
