"""Produttore dal sysObjectID (il numero dopo 1.3.6.1.4.1 è l'enterprise number IANA) e modello da un testo libero
(sysDescr, descrizione dello chassis) per gli apparati che non lo danno in ENTITY-MIB."""
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


# Nome dato da NetMap a un produttore che non conosce: si corregge appena una regola SNMP dice quello vero
PROVISIONAL_MANUFACTURER = re.compile(r"^Enterprise \d+$")


def vendor_name(sys_object_id: str | None) -> str:
    number = enterprise_number(sys_object_id)
    if number is None:
        return "Sconosciuto"
    return ENTERPRISES.get(number, f"Enterprise {number}")


def manufacturer_of(hd) -> str | None:
    """Produttore di un apparato letto (snmp.HostData): quello di una regola SNMP, altrimenti dal sysObjectID."""
    return hd.manufacturer or (vendor_name(hd.sys_object_id) if hd.sys_object_id else None)


# HP / HPE / Aruba: codice prodotto (J9728A, JL254A, R8N88A) o, senza codice, il nome dopo la marca ("HP 1810-24")
_HP_DESCR = re.compile(r"\b(?:HPE?|Hewlett[- ]Packard|ProCurve|Aruba)\b", re.IGNORECASE)
_HP_PRODUCT = re.compile(r"\b((?:J[A-Z]?\d{3,4}|R\d[A-Z]\d{2})[A-Z])\b")
_HP_NAME = re.compile(r"^(?:HPE?|Hewlett[- ]Packard|ProCurve|Aruba)\s+(?:OfficeConnect\s+)?(?:Switch\s+)?"
                      r"([A-Za-z]*\d[\w+-]*)", re.IGNORECASE)


# Codice "da modello": lettere e cifre, eventualmente con - + /, senza punti (sarebbe una versione)
_MODEL_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9+/-]*$")
# Parole con lettere e cifre che non sono modelli: velocità e porte (10G, 48x1G, 250W, 24-port), standard e
# moduli (1000BASE-T, SFP28, 802.3at), versioni (v5, V200R011, v1535b2-patch1), processori e chip (ARMv7, 24Kc, ipq9574,
# RTL8380), immagini Cisco (C3750-IPBASE-M, fc1), marche con una cifra nel nome, date (08-Sep-2009)
_NOT_MODEL = re.compile(
    r"^(?:\d+(?:x\d+)?[a-z]{0,4}\d*(?:[+/]\d+(?:x\d+)?[a-z]{0,4}\d*)*|\d+-?ports?|\d+-bit|\d+base-?\w*|q?sfp\w*|802\w*"
    r"|ipv\d|v\d.*|os\d+|armv\d+\w*|mips\w*|x86\w*|ppc\w*|i\d86|(?:ipq|rtl|bcm|qca|mt7)\d+.*"
    r"|.*k9.*|.*(?:universal|ipbase|ipservices|entservices|enterprise|lanbase|lanlite).*|fc\d+"
    r"|nexus\d+|class\d+|layer\d\+?|3com|force10|h3c|pica8|\d+-[a-z]{3}-\d+)$",
    re.IGNORECASE)
# Dopo queste parole viene una versione o un'immagine, non il modello ("Release 2422P01", "Software (C2960-...)")
_VERSION_WORDS = {"release", "version", "ver", "rev", "revision", "build", "built", "firmware", "fw", "sw", "hw",
                  "bootrom", "rom", "boot", "bootloader", "kernel", "linux", "software", "primary", "backup",
                  "compiled", "serial", "sn"}


def _model_token(tokens: list[str]) -> str | None:
    previous = ""
    for raw in tokens:
        token = raw.strip("\"',;:.()[]")
        if (3 <= len(token) <= 32 and _MODEL_TOKEN.match(token) and re.search(r"\d", token)
                and re.search(r"[A-Za-z]", token) and not _NOT_MODEL.match(token)
                and (previous.endswith(",") or previous.lower().strip("\"';:.()[]") not in _VERSION_WORDS)):
            return token
        previous = raw
    return None


def model_from_text(text: str | None) -> str | None:
    """Primo codice che sembra un modello in un testo libero (sysDescr, descrizione dello chassis).

    Regola unica per tutte le marche, provata sulle descrizioni di circa 500 switch veri: GS1900-24, ECS2100-28P,
    "RouterOS ... on RB760iGS", "ExtremeXOS (X440-24p)", "Huawei AR1220 ...". None se non c'è niente di convincente:
    meglio nessun modello (resta il sysObjectID) che uno sbagliato.
    """
    if not text:
        return None
    text = " ".join(text.replace(",", ", ").replace("(", " (").split())
    after_on = re.search(r"(?<!compiled )\bon (.+)", text, re.IGNORECASE)  # "running on an Arista Networks DCS-7280"
    if after_on and (token := _model_token(after_on.group(1).split()[:4])):
        return token
    if token := _model_token(text.split()[:12]):
        return token
    for group in re.findall(r"\(([^()]*)", text):  # "Ruijie 10G Routing Switch(S6150-24VS8CQ-X)"
        if token := _model_token(group.split()[:2]):
            return token
    return None


def model_from_descr(sys_descr: str | None) -> str | None:
    """Modello letto dal sysDescr, per gli apparati che non lo danno in ENTITY-MIB (es. HP 1810, 1820, 1910, Zyxel,
    Netgear, D-Link): altrimenti il modello nuovo si chiamerebbe con il sysObjectID. Per HP prima il codice prodotto
    (J9979A), poi la regola generica."""
    if not sys_descr:
        return None
    if _HP_DESCR.search(sys_descr):
        product = _HP_PRODUCT.search(sys_descr)
        if product:
            return product.group(1)
        name = _HP_NAME.match(sys_descr.strip())
        if name:
            return name.group(1).rstrip(",")
    return model_from_text(sys_descr)
