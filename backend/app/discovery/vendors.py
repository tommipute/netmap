"""Produttore dal sysObjectID: il numero dopo 1.3.6.1.4.1 è l'enterprise number IANA."""

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
