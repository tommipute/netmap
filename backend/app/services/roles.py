"""Tipo di apparato e ruolo proposto per i modelli che la scansione trova.

Il tipo (stampante, UPS, access point, switch…) si riconosce da più segnali, dal più sicuro al più vago:
le MIB standard che solo certi apparati hanno (Printer-MIB, UPS-MIB), le parole della descrizione SNMP e del
modello, il produttore (sysObjectID), le capacità che il device dichiara in LLDP e sysServices (livelli OSI).
Il ruolo è quello esistente che ha il nome giusto (per parole); se non c'è, se ne propone uno nuovo con il nome
del tipo, che si crea approvando il device.
"""
import re
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.discovery.vendors import enterprise_number
from app.models import DeviceRole


@dataclass(frozen=True)
class Kind:
    key: str
    role: str  # nome del ruolo da creare se non ce n'è uno adatto
    words: tuple[str, ...]  # parole nel nome di un ruolo esistente, in ordine di priorità
    level: int  # livello in mappa del ruolo nuovo (0 = in alto)
    color: str
    pattern: re.Pattern | None = None  # parole della descrizione SNMP / del modello
    enterprises: tuple[int, ...] = ()  # produttori che fanno solo questo tipo di apparato


def _re(text: str) -> re.Pattern:
    return re.compile(text, re.I)


# In ordine: vince il primo che corrisponde (firewall prima di router, access point prima di switch, i tipi con
# parole molto precise prima degli access point: "AP8853" è un PDU APC)
KINDS = [
    Kind("firewall", "Firewall", ("firewall", "fw"), 0, "#E24B4A",
         _re(r"fortigate|fortinet|\basa\s?\d|firepower|palo ?alto|pan-os|\bsrx\d|pfsense|opnsense|sonicwall|check ?point|sophos|watchguard"),
         (12356, 25461, 8741, 2620, 21067)),  # Fortinet, Palo Alto, SonicWall, Check Point, Sophos
    Kind("wlc", "Controller wireless", ("controller wireless", "wireless controller", "wlc", "controller"), 1, "#F59E0B",
         _re(r"wireless (lan )?controller|\bwlc\b|\bc9800\b|\bair-ct\d|mobility controller")),
    Kind("phone", "Telefono", ("telefono", "telefoni", "phone", "voip"), 4, "#8B5CF6",
         _re(r"ip phone|\bsip-?t\d|yealink|polycom|snom|grandstream|\bcp-\d{4}|mitel|gigaset"),
         (37459, 3990)),  # Yealink, Snom
    Kind("camera", "Telecamera", ("telecamera", "telecamere", "camera", "videosorveglianza", "tvcc"), 4, "#64748B",
         _re(r"network camera|ip camera|\baxis\b|hikvision|dahua|\bnvr\b|\bdvr\b|vivotek|hanwha|mobotix"),
         (368, 39165, 1004849)),  # Axis, Hikvision, Dahua
    Kind("printer", "Stampante", ("stampante", "stampanti", "printer", "stampa"), 4, "#0EA5E9",
         _re(r"printer|laserjet|officejet|jetdirect|\bmfp\b|imagerunner|bizhub|ricoh|kyocera|xerox|brother nc|lexmark|epson|konica|sharp mx|canon ir"),
         (1602, 2435, 367, 1347, 253, 641, 18334)),  # Canon, Brother, Ricoh, Kyocera, Xerox, Lexmark, Konica
    Kind("ups", "UPS", ("ups", "gruppo di continuità", "continuità"), 3, "#DC2626",
         _re(r"\bups\b|smart-ups|symmetra|powerware|eaton (5|9)|network management card|netman|riello|\bups-mib|powerchute"),
         (534, 705, 5491)),  # Eaton/Powerware, Socomec, Riello
    Kind("pdu", "PDU", ("pdu", "ciabatta", "alimentazione"), 3, "#B45309",
         _re(r"\bpdu\b|rack pdu|power distribution|raritan|servertech|sentry")),
    Kind("nas", "NAS", ("nas", "storage", "archiviazione"), 3, "#0F766E",
         _re(r"synology|diskstation|rackstation|qnap|readynas|truenas|freenas|\bnas\b|netapp|data ontap|powervault|storeonce"),
         (6574, 24681, 789)),  # Synology, QNAP, NetApp
    Kind("ap", "Access point", ("access point", "ap", "wifi", "wi-fi", "wireless"), 3, "#F59E0B",
         _re(r"access point|aironet|\bair-|\bc9[12]\d\dax|unifi ap|\buap\b|aruba ap|\bap-?\d{3}|instant on ap|wireless lan|\bu6-|\bu7-|ruckus|cambium|eap\d{3}"),
         (25053,)),  # Ruckus
    Kind("router", "Router", ("router", "gateway", "gw"), 0, "#E24B4A",
         _re(r"\brouter\b|\bisr\s?\d|\basr\s?\d|routeros|mikrotik|edgerouter|vyos|\bc8[0-9]{3}|draytek|vigor")),
    Kind("switch", "Switch", ("switch", "accesso", "access", "distribuzione", "core"), 2, "#1D9E75",
         _re(r"switch|catalyst|procurve|aruba|nexus|\bc1000|\bc9[2-5]00|\b29[23]0f?|\bex\d{4}|icx\d|powerconnect|os6\d{3}|comware|\bsg\d{3}|\bcbs\d{3}|netgear gs|\btl-sg|unifi switch|\busw-")),
    Kind("server", "Server", ("server", "host", "hypervisor"), 3, "#64748B",
         _re(r"windows|vmware esxi|\besxi\b|hyper-v|proxmox|ubuntu|debian|red hat|centos|\bidrac\b|\bilo\b|xclarity")),
]
BY_KEY = {k.key: k for k in KINDS}

@dataclass(frozen=True)
class Detected:
    kind: Kind
    reason: str  # da dove si è capito (si vede nella proposta)


def detect_kind(*, sys_descr: str | None = None, model: str | None = None, sys_object_id: str | None = None,
                mibs: list[str] | tuple = (), caps: list[str] | tuple = (), sys_services: int | None = None,
                extra: str | None = None) -> Detected | None:
    """Tipo di apparato dai segnali della scansione; None se non si capisce."""
    if "printer" in mibs:
        return Detected(BY_KEY["printer"], "Printer-MIB")
    if "ups" in mibs:
        return Detected(BY_KEY["ups"], "UPS-MIB")
    text = " ".join(t for t in (sys_descr, model, extra) if t)
    for kind in KINDS:
        if kind.pattern and text and kind.pattern.search(text):
            return Detected(kind, "descrizione SNMP")
    number = enterprise_number(sys_object_id)
    for kind in KINDS:
        if number is not None and number in kind.enterprises:
            return Detected(kind, "produttore")
    if "wlanAccessPoint" in caps:
        return Detected(BY_KEY["ap"], "LLDP")
    if "telephone" in caps:
        return Detected(BY_KEY["phone"], "LLDP")
    if "bridge" in caps:
        return Detected(BY_KEY["switch"], "LLDP")
    if "router" in caps:
        return Detected(BY_KEY["router"], "LLDP")
    if sys_services:
        if sys_services & 2:  # livello 2: fa da bridge
            return Detected(BY_KEY["switch"], "sysServices")
        if sys_services & 4 and not sys_services & 64:  # livello 3 senza applicazioni
            return Detected(BY_KEY["router"], "sysServices")
    return None


def _matches(role_name: str, words: tuple[str, ...] | list[str]) -> bool:
    name = role_name.lower()
    return any(re.search(rf"(^|\W){re.escape(w)}($|\W)", name) for w in words)


def role_for(db: Session, kind: Kind) -> DeviceRole | None:
    """Ruolo esistente adatto al tipo: parole in ordine di priorità ("Switch di accesso" prima di "accesso")."""
    roles = list(db.scalars(select(DeviceRole).order_by(DeviceRole.level, DeviceRole.name)))
    for word in kind.words:
        role = next((r for r in roles if _matches(r.name, [word])), None)
        if role:
            return role
    return None


def guess_role(db: Session, *texts: str | None) -> DeviceRole | None:
    """Ruolo esistente dalle sole parole (descrizione SNMP, produttore, modello); None se non c'è."""
    detected = detect_kind(extra=" ".join(t for t in texts if t))
    return role_for(db, detected.kind) if detected else None
