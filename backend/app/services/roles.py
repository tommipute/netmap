"""Ruolo proposto per i modelli che la scansione trova: si indovina dalla descrizione SNMP e dal nome del modello,
scegliendo tra i ruoli che esistono già (per nome). Se non si riconosce niente, nessun ruolo."""
import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import DeviceRole

# Tipo di apparato: parole della descrizione SNMP / del modello, poi parole nel nome del ruolo
KINDS = [
    ("firewall", re.compile(r"fortigate|fortinet|\basa\s?\d|firepower|palo ?alto|pan-os|\bsrx\d|pfsense|opnsense|sonicwall|check ?point|sophos|watchguard", re.I),
     ["firewall", "fw"]),
    ("access point", re.compile(r"access point|aironet|\bair-|\bc9[12]\d\dax|unifi ap|\buap\b|aruba ap|\bap-?\d{3}|instant on ap|wireless lan", re.I),
     ["access point", "ap", "wifi", "wi-fi", "wireless"]),
    ("router", re.compile(r"\brouter\b|\bisr\s?\d|\basr\s?\d|routeros|mikrotik|edgerouter|vyos", re.I),
     ["router"]),
    ("switch", re.compile(r"switch|catalyst|procurve|aruba|nexus|\bc1000|\bc9[2-5]00|\b29[23]0f?|\bex\d{4}|icx\d|powerconnect|os6\d{3}", re.I),
     ["switch", "accesso"]),
]


def _matches(role_name: str, words: list[str]) -> bool:
    name = role_name.lower()
    return any(re.search(rf"(^|\W){re.escape(w)}($|\W)", name) for w in words)


def guess_role(db: Session, *texts: str | None) -> DeviceRole | None:
    text = " ".join(t for t in texts if t)
    if not text:
        return None
    roles = list(db.scalars(select(DeviceRole).order_by(DeviceRole.level, DeviceRole.name)))
    for _kind, pattern, words in KINDS:
        if pattern.search(text):
            # Parole in ordine di priorità: "Switch di accesso" prima di un ruolo che dice solo "accesso"
            for word in words:
                role = next((r for r in roles if _matches(r.name, [word])), None)
                if role:
                    return role
            return None
    return None
