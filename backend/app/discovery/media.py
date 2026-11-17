"""Rame o fibra di una porta, dal modulo inserito (SFP, SFP+, QSFP…) o dalla descrizione della porta.

L'ifType non lo dice (Ethernet è Ethernet), ma gli switch descrivono il modulo: "10G_BASE_SR_SFP" (HPE Comware),
"SFP+LR" (Aruba/ProCurve), "SFP-10GBase-LR", "QSFP 40GE CU1M" (ENTITY-MIB), "HP J9989A 1000BASE-SX Port".
Da quel testo si ricava il tipo della porta (copper/fiber) e quello del cavo (fiber_sm, fiber_mm, dac o niente).
"""
import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Media:
    port: str               # copper / fiber
    cable: str | None       # fiber_sm / fiber_mm / dac / None (rame RJ45: Cat5e o Cat6 non si sa)
    module: str | None = None  # testo del modulo da cui si è ricavato, per la scheda "Cosa ho letto"


def _token(words: str) -> re.Pattern:
    """Parola staccata da lettere (le cifre attorno vanno bene: "1000LX", "SR4", "CU1M")."""
    return re.compile(rf"(?<![A-Z])(?:{words})(?![A-Z])")


# In ordine: il cavo integrato (DAC, AOC) prima delle sigle delle ottiche, il rame RJ45 prima della fibra generica.
# "SM"/"MM" da soli valgono solo staccati dai numeri: "(0.009mm)" è il diametro in millimetri (Huawei)
_BARE = r"(?<![A-Z0-9.])(?:{})(?![A-Z])"
_RULES = [
    (_token(r"CU\d*(?:\.\d+)?M?|CX\d*|DAC|TWINAX|DIRECT ATTACH|PIGTAIL"), "copper", "dac"),
    (_token(r"AOC\d*M?"), "fiber", "fiber_mm"),
    (_token(r"BASE ?T|BASE ?TX|RJ ?45|1000T|10GT|COPPER"), "copper", None),
    (re.compile(_BARE.format("MM") + "|" + _token(
        r"LRM|SX|SR\d*|SWDM\d*|FX|MMF|MULTI ?MODE FIB\w*|OM[1-5]|50 ?UM|62\.5 ?UM|8\d\d ?NM|0\.05 ?MM|0\.0625 ?MM"
    ).pattern), "fiber", "fiber_mm"),
    (re.compile(_BARE.format("SM") + "|" + _token(
        r"LX\d*|LR\d*|ER\d*|ZR\d*|EX|BX\d*|LH|SMF|SINGLE ?MODE FIB\w*|OS[12]|9 ?UM|1[2-6]\d\d ?NM|0\.009 ?MM"
    ).pattern), "fiber", "fiber_sm"),
    (_token(r"LC|SC|MPO|FIBER|FIBRE|OPTIC(?:AL|S)?"), "fiber", None),
]


def media_from_text(*texts: str | None) -> Media | None:
    """Rame o fibra dal primo testo che lo dice. None se nessuno lo dice (slot vuoto, descrizione generica)."""
    for text in texts:
        if not text:
            continue
        norm = re.sub(r"BASE-?", " BASE ", text.upper().replace("_", " "))
        for pattern, port, cable in _RULES:
            if pattern.search(norm):
                return Media(port, cable, " ".join(text.split())[:80])
    return None


# HH3C-TRANSCEIVER-INFO-MIB: hh3cTransceiverFiberDiameterType
_HH3C_DIAMETER = {1: ("fiber", "fiber_sm"), 2: ("fiber", "fiber_mm"), 3: ("fiber", "fiber_mm"), 4: ("copper", "dac")}


def media_hh3c(hardware: str | None, kind: str | None, diameter: int | None) -> Media | None:
    """Modulo di uno switch HPE Comware/H3C: tipo ("10G_BASE_SR_SFP"), fibra ("SM"/"MM") e diametro (1 = 9 µm…)."""
    found = media_from_text(kind, hardware)
    if found is None and diameter in _HH3C_DIAMETER:
        port, cable = _HH3C_DIAMETER[diameter]
        found = Media(port, cable, kind or hardware)
    return found
