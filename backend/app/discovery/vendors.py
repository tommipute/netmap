"""Produttore dal sysObjectID (il numero dopo 1.3.6.1.4.1 è l'enterprise number IANA) e modello dal sysDescr per
gli apparati senza ENTITY-MIB."""
import re

ENTERPRISE_PREFIX = "1.3.6.1.4.1."

ENTERPRISES = {
    2: "IBM",
    9: "Cisco",
    11: "HPE",
    171: "D-Link",
    207: "Allied Telesis",
    311: "Microsoft",
    674: "Dell",
    890: "Zyxel",
    1916: "Extreme Networks",
    1991: "Brocade",
    2011: "Huawei",
    2620: "Check Point",
    2636: "Juniper",
    3375: "F5",
    4526: "Netgear",
    5624: "Enterasys",
    6027: "Dell (Force10)",
    6486: "Alcatel-Lucent",
    6527: "Nokia",
    6876: "VMware",
    8072: "Net-SNMP",
    8741: "SonicWall",
    10002: "Ubiquiti",
    11863: "TP-Link",
    12356: "Fortinet",
    14823: "HPE Aruba",
    14988: "MikroTik",
    25461: "Palo Alto Networks",
    25506: "H3C",
    30065: "Arista",
    41112: "Ubiquiti",
    47196: "HPE Aruba",
}


def enterprise_number(sys_object_id: str | None) -> int | None:
    if not sys_object_id or not sys_object_id.startswith(ENTERPRISE_PREFIX):
        return None
    first = sys_object_id[len(ENTERPRISE_PREFIX):].split(".", 1)[0]
    return int(first) if first.isdigit() else None


def vendor_name(sys_object_id: str | None) -> str:
    number = enterprise_number(sys_object_id)
    if number is None:
        return "Sconosciuto"
    return ENTERPRISES.get(number, f"Enterprise {number}")


# HP / HPE / Aruba: codice prodotto (J9728A, JL254A, R8N88A) o, senza codice, il nome dopo la marca ("HP 1810-24")
_HP_DESCR = re.compile(r"\b(?:HPE?|Hewlett[- ]Packard|ProCurve|Aruba)\b", re.IGNORECASE)
_HP_PRODUCT = re.compile(r"\b((?:J[A-Z]?\d{3,4}|R\d[A-Z]\d{2})[A-Z])\b")
_HP_NAME = re.compile(r"^(?:HPE?|Hewlett[- ]Packard|ProCurve|Aruba)\s+(?:OfficeConnect\s+)?(?:Switch\s+)?"
                      r"([A-Za-z]*\d[\w+-]*)", re.IGNORECASE)


def model_from_descr(sys_descr: str | None) -> str | None:
    """Modello letto dal sysDescr, per gli apparati che non lo danno in ENTITY-MIB (es. HP 1810, 1820, 1910):
    altrimenti il modello nuovo si chiamerebbe con il sysObjectID. Per ora solo HP/HPE/Aruba."""
    if not sys_descr or not _HP_DESCR.search(sys_descr):
        return None
    product = _HP_PRODUCT.search(sys_descr)
    if product:
        return product.group(1)
    name = _HP_NAME.match(sys_descr.strip())
    return name.group(1).rstrip(",") if name else None
