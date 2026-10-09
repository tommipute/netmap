"""Import da NetBox (solo admin), eseguito dal worker (thread import_loop).

Il worker legge con le API REST di NetBox (basta un token in sola lettura) e crea in NetMap quello che manca:
sedi, posizioni, rack, produttori, ruoli, modelli, VRF, VLAN, subnet, device con porte e stack, cavi, IP.

- Ogni oggetto si cerca in NetMap per chiave naturale (sede per nome, rack per sede e nome, device per sede e
  nome, IP per VRF e indirizzo...): se c'è già resta com'è, si crea solo quello che manca. Le porte si creano solo
  sui device creati adesso; quelle dei device che c'erano già si cercano per nome (servono a cavi e IP).
- Uno stack di NetBox (virtual chassis) diventa un device solo con i suoi membri, come nella scansione SNMP.
- Cavi tra porte: passano. Attraverso i patch panel: un cavo da porta a porta con i patch panel nella
  descrizione (NetMap non ha porte frontali e posteriori). Verso circuiti, prese elettriche e console: no.
- Prima si legge tutto da NetBox (il log si vede man mano), poi si scrive in una transazione sola: una
  simulazione o un errore tornano indietro senza lasciare niente. Ogni oggetto ha il suo SAVEPOINT e passa dagli
  stessi controlli dei moduli (schemi e hook di rules.py): uno sbagliato finisce tra i problemi, gli altri passano.
"""
import ipaddress
import json
import logging
import math
import re
import ssl
import time
import urllib.error
import urllib.request
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlencode, urlsplit

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import DataError, IntegrityError, OperationalError, ProgrammingError
from sqlalchemy.orm import Session

from app.api.crud import apply_data
from app.core.net import normalize_ip_interface, normalize_mac, normalize_prefix
from app.core.secrets import SecretError, decrypt
from app.models import (
    VLAN, VRF, Cable, Device, DeviceRole, DeviceType, ImportRun, Interface, IPAddress, Location, Manufacturer, Prefix,
    Rack, Site, StackMember,
)
from app.models.enums import RunStatus
from app.schemas import dcim as d
from app.schemas import ipam as i
from app.services import rules
from app.services.device_import_export import guess_role_style

logger = logging.getLogger("netmap.netbox")

PAGE_SIZE = 1000      # massimo di NetBox (MAX_PAGE_SIZE); se il server ne dà meno si va avanti con l'offset
TIMEOUT = 60          # secondi per pagina
MAX_PROBLEMS = 1000   # oltre, il log dice quanti ne mancano
POLL_SECONDS = 3
KEEP_RUNS = 20        # import tenuti nello storico della pagina
MIN_VERSION = (3, 3)  # link_peers e connected_endpoints sulle porte

KINDS = ("site", "location", "rack", "manufacturer", "device_role", "device_type", "vrf", "vlan", "prefix",
         "device", "stack_member", "interface", "cable", "ip")


class NetBoxError(Exception):
    """NetBox non raggiungibile o risposta inattesa: il messaggio va all'utente."""


def now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------- client
def normalize_url(url: str) -> str:
    url = url.strip().rstrip("/")
    if url.endswith("/api"):
        url = url[:-4]
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        raise NetBoxError("Indirizzo non valido: serve http:// o https:// seguito dal nome del server")
    return url


def _detail(exc: urllib.error.HTTPError) -> str:
    try:
        data = json.loads(exc.read() or b"{}")
    except (ValueError, OSError):
        return ""
    return str(data.get("detail") or "")[:200] if isinstance(data, dict) else ""


class Client:
    def __init__(self, url: str, token: str, verify_tls: bool = True):
        self.base = normalize_url(url)
        token = token.strip()
        scheme = "Bearer" if token.startswith("nbt_") else "Token"  # token v2 (NetBox 4.5+) o v1
        self.headers = {"Authorization": f"{scheme} {token}", "Accept": "application/json", "User-Agent": "NetMap"}
        self.context = ssl.create_default_context()
        if not verify_tls:
            self.context.check_hostname = False
            self.context.verify_mode = ssl.CERT_NONE

    def get(self, path: str, params: dict | None = None) -> Any:
        url = f"{self.base}/api/{path}/" + (f"?{urlencode(params, doseq=True)}" if params else "")
        request = urllib.request.Request(url, headers=self.headers)
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT, context=self.context) as response:
                body = response.read()
        except urllib.error.HTTPError as exc:
            detail = _detail(exc)
            if exc.code in (401, 403):
                raise NetBoxError(f"NetBox rifiuta il token ({detail or exc.code}): controlla che sia giusto, "
                                  "non scaduto e con il permesso di lettura") from exc
            if exc.code == 404:
                raise NetBoxError(f"NetBox non trova /api/{path}/: l'indirizzo è quello di NetBox?") from exc
            raise NetBoxError(f"NetBox ha risposto {exc.code} su /api/{path}/" + (f": {detail}" if detail else "")) from exc
        except urllib.error.URLError as exc:
            if isinstance(exc.reason, ssl.SSLCertVerificationError):
                raise NetBoxError(f"Il certificato HTTPS di NetBox non è valido ({exc.reason.verify_message}): "
                                  "usa il nome giusto del server o togli la verifica del certificato") from exc
            raise NetBoxError(f"NetBox non risponde ({exc.reason})") from exc
        except OSError as exc:  # timeout, connessione chiusa
            raise NetBoxError(f"NetBox non risponde ({exc})") from exc
        try:
            return json.loads(body)
        except ValueError as exc:
            raise NetBoxError("La risposta non è JSON: l'indirizzo è quello di NetBox?") from exc

    def all(self, path: str, params: dict | None = None, keep: Callable[[dict], dict] | None = None) -> list[dict]:
        """Tutte le pagine di un elenco. keep riduce ogni oggetto ai campi che servono (meno memoria)."""
        items: list[dict] = []
        offset = 0
        while True:
            data = self.get(path, {**(params or {}), "limit": PAGE_SIZE, "offset": offset})
            results = data.get("results") if isinstance(data, dict) else None
            if not isinstance(results, list):
                raise NetBoxError(f"Risposta inattesa da /api/{path}/: l'indirizzo è quello di NetBox?")
            items.extend(keep(item) if keep else item for item in results)
            offset += len(results)
            if not results or not data.get("next"):
                return items

    def count(self, path: str, params: dict | None = None) -> int:
        data = self.get(path, {**(params or {}), "limit": 1, "brief": 1})
        return int(data.get("count") or 0) if isinstance(data, dict) else 0

    def version(self) -> str:
        data = self.get("status")
        version = data.get("netbox-version") if isinstance(data, dict) else None
        if not version:
            raise NetBoxError("Non sembra NetBox: /api/status/ non dice la versione")
        numbers = tuple(int(n) for n in re.findall(r"\d+", str(version))[:2])
        if numbers < MIN_VERSION:
            raise NetBoxError(f"NetBox {version} è troppo vecchio: serve la versione 3.3 o successiva")
        return str(version)


def probe(client: Client) -> dict:
    """Prova della connessione: versione, quanti oggetti ci sono e le sedi da scegliere."""
    version = client.version()
    sites = client.all("dcim/sites", keep=lambda s: {
        "id": s.get("id"), "name": _str(s.get("name")), "devices": s.get("device_count") or 0,
    })
    counts = {key: client.count(path) for key, path in (
        ("devices", "dcim/devices"), ("interfaces", "dcim/interfaces"), ("cables", "dcim/cables"),
        ("vlans", "ipam/vlans"), ("prefixes", "ipam/prefixes"), ("ip_addresses", "ipam/ip-addresses"),
    )}
    counts["sites"] = len(sites)
    return {"version": version, "counts": counts, "sites": sorted(sites, key=lambda s: s["name"].lower())}


# ---------------------------------------------------------------- lettura (oggetti ridotti ai campi che servono)
def _ref(value: Any) -> Any:
    return value.get("id") if isinstance(value, dict) else value


def _choice(value: Any) -> Any:
    return value.get("value") if isinstance(value, dict) else value


def _str(value: Any, limit: int | None = None) -> str:
    text = value.strip() if isinstance(value, str) else ""
    return text[:limit] if limit else text


def _label(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("name") or value.get("display") or value.get("id") or "")
    return str(value)


def _custom_fields(item: dict) -> dict:
    """Campi personalizzati di NetBox come testo (un oggetto collegato diventa il suo nome)."""
    out = {}
    for key, value in (item.get("custom_fields") or {}).items():
        if value is None or value == "" or value == [] or value == {}:
            continue
        if isinstance(value, bool):
            value = "true" if value else "false"
        elif isinstance(value, list):
            value = ", ".join(_label(v) for v in value)
        elif isinstance(value, dict):
            value = _label(value)
        out[str(key)[:100]] = str(value)
    return out


def _common(item: dict) -> dict:
    return {"id": item.get("id"), "description": _str(item.get("description")), "cf": _custom_fields(item)}


def _site(s: dict) -> dict:
    return {**_common(s), "name": _str(s.get("name"), 100), "address": _str(s.get("physical_address"), 255)}


def _location(loc: dict) -> dict:
    return {**_common(loc), "name": _str(loc.get("name"), 100), "site": _ref(loc.get("site")),
            "parent": _ref(loc.get("parent")), "depth": loc.get("_depth") or 0}


def _rack(r: dict) -> dict:
    return {**_common(r), "name": _str(r.get("name"), 100), "site": _ref(r.get("site")),
            "location": _ref(r.get("location")), "u_height": r.get("u_height")}


def _manufacturer(m: dict) -> dict:
    return {"id": m.get("id"), "name": _str(m.get("name"), 100)}


def _role(r: dict) -> dict:
    return {**_common(r), "name": _str(r.get("name"), 100), "color": _str(r.get("color"))}


def _device_type(t: dict) -> dict:
    return {**_common(t), "manufacturer": _ref(t.get("manufacturer")), "model": _str(t.get("model"), 100),
            "part_number": _str(t.get("part_number"), 100), "u_height": t.get("u_height")}


def _vrf(v: dict) -> dict:
    return {**_common(v), "name": _str(v.get("name"), 100), "rd": _str(v.get("rd"), 50)}


def _vlan_group(g: dict) -> dict:
    return {"id": g.get("id"), "scope_type": g.get("scope_type"), "scope_id": g.get("scope_id")}


def _vlan(v: dict) -> dict:
    return {**_common(v), "vid": v.get("vid"), "name": _str(v.get("name"), 100), "site": _ref(v.get("site")),
            "group": _ref(v.get("group")), "status": _choice(v.get("status"))}


def _prefix(p: dict) -> dict:
    return {**_common(p), "prefix": _str(p.get("prefix")), "vrf": _ref(p.get("vrf")), "site": _ref(p.get("site")),
            "scope_type": p.get("scope_type"), "scope_id": p.get("scope_id"), "vlan": _ref(p.get("vlan")),
            "status": _choice(p.get("status"))}


def _chassis(c: dict) -> dict:
    return {"id": c.get("id"), "name": _str(c.get("name"), 100), "master": _ref(c.get("master"))}


def _device(x: dict) -> dict:
    device_type = x.get("device_type") or {}
    return {
        **_common(x), "name": _str(x.get("name"), 100), "display": _str(x.get("display"), 100),
        "site": _ref(x.get("site")), "location": _ref(x.get("location")), "rack": _ref(x.get("rack")),
        "position": x.get("position"), "device_type": _ref(device_type),
        "model": _str(device_type.get("model"), 100) if isinstance(device_type, dict) else "",
        "role": _ref(x.get("role") or x.get("device_role")), "status": _choice(x.get("status")),
        "serial": _str(x.get("serial"), 100), "asset_tag": _str(x.get("asset_tag"), 100),
        "primary_ip4": _ref(x.get("primary_ip4")), "primary_ip6": _ref(x.get("primary_ip6")),
        "vc": _ref(x.get("virtual_chassis")), "vc_position": x.get("vc_position"),
    }


def _interface(x: dict) -> dict:
    device = x.get("device") or {}
    mac = x.get("mac_address") or (x.get("primary_mac_address") or {}).get("mac_address")
    return {
        **_common(x), "device": _ref(device), "device_name": _label(device), "name": _str(x.get("name"), 100),
        "type": _choice(x.get("type")) or "", "enabled": x.get("enabled") is not False,
        "mgmt_only": bool(x.get("mgmt_only")), "mac": mac, "speed": x.get("speed"), "mtu": x.get("mtu"),
        "mode": _choice(x.get("mode")), "untagged": _ref(x.get("untagged_vlan")),
        "tagged": [_ref(v) for v in x.get("tagged_vlans") or []], "lag": _ref(x.get("lag")),
        "cable": _ref(x.get("cable")), "peers_type": x.get("link_peers_type"),
        "peers": [{"id": p.get("id"), "device": _label(p.get("device") or {})}
                  for p in x.get("link_peers") or [] if isinstance(p, dict)],
        "endpoints_type": x.get("connected_endpoints_type"),
        "endpoints": [e.get("id") for e in x.get("connected_endpoints") or [] if isinstance(e, dict)],
    }


def _cable(c: dict) -> dict:
    return {**_common(c), "type": c.get("type") or "", "status": _choice(c.get("status")),
            "label": _str(c.get("label"), 100), "color": _str(c.get("color")), "length": c.get("length"),
            "length_unit": _choice(c.get("length_unit"))}


def _ip(x: dict) -> dict:
    return {**_common(x), "address": _str(x.get("address")), "vrf": _ref(x.get("vrf")),
            "status": _choice(x.get("status")), "dns_name": _str(x.get("dns_name"), 255),
            "assigned_type": x.get("assigned_object_type"), "assigned_id": x.get("assigned_object_id")}


@dataclass
class Snapshot:
    sites: list[dict]
    locations: list[dict]
    racks: list[dict]
    manufacturers: list[dict]
    roles: list[dict]
    device_types: list[dict]
    vrfs: list[dict]
    vlan_groups: list[dict]
    vlans: list[dict]
    prefixes: list[dict]
    chassis: list[dict]
    devices: list[dict]
    interfaces: list[dict]
    cables: list[dict]
    ips: list[dict]


def fetch(client: Client, site_ids: set[int] | None, progress: Callable[[str], None]) -> Snapshot:
    """Legge da NetBox tutto quello che serve. Con le sedi scelte, il filtro lo fa NetBox dove può."""
    by_site = {"site_id": sorted(site_ids)} if site_ids else {}

    def load(path: str, keep: Callable[[dict], dict], params: dict | None = None) -> list[dict]:
        items = client.all(path, params, keep)
        progress(f"Letti da NetBox: {path} ({len(items)})")
        return items

    snap = Snapshot(
        sites=load("dcim/sites", _site, {"id": sorted(site_ids)} if site_ids else None),
        locations=load("dcim/locations", _location, by_site),
        racks=load("dcim/racks", _rack, by_site),
        manufacturers=load("dcim/manufacturers", _manufacturer),
        roles=load("dcim/device-roles", _role),
        device_types=load("dcim/device-types", _device_type),
        vrfs=load("ipam/vrfs", _vrf),
        vlan_groups=load("ipam/vlan-groups", _vlan_group),
        vlans=load("ipam/vlans", _vlan),
        prefixes=load("ipam/prefixes", _prefix),
        chassis=load("dcim/virtual-chassis", _chassis),
        devices=load("dcim/devices", _device, {**by_site, "exclude": "config_context"}),
        interfaces=load("dcim/interfaces", _interface, by_site),
        cables=load("dcim/cables", _cable, by_site),
        ips=load("ipam/ip-addresses", _ip),
    )
    if site_ids:  # del catalogo solo quello che usano i device delle sedi scelte
        types = {x["device_type"] for x in snap.devices}
        snap.device_types = [t for t in snap.device_types if t["id"] in types]
        makers = {t["manufacturer"] for t in snap.device_types}
        snap.manufacturers = [m for m in snap.manufacturers if m["id"] in makers]
        roles = {x["role"] for x in snap.devices}
        snap.roles = [r for r in snap.roles if r["id"] in roles]
    return snap


# ---------------------------------------------------------------- traduzione dei valori di NetBox
DEVICE_STATUS = {"active": "active", "planned": "planned", "staged": "planned", "offline": "offline",
                 "failed": "offline", "inventory": "offline", "decommissioning": "decommissioned"}
IPAM_STATUS = {"active": "active", "container": "active", "reserved": "reserved", "deprecated": "deprecated"}
IP_STATUS = {"active": "active", "reserved": "reserved", "deprecated": "deprecated", "dhcp": "dhcp", "slaac": "active"}
CABLE_STATUS = {"connected": "connected", "planned": "planned", "decommissioning": "decommissioning"}
WIRELESS = ("ieee802.11", "ieee802.15", "other-wireless", "gsm", "cdma", "lte", "4g", "5g")


def interface_type(value: str) -> str:
    value = (value or "").lower()
    if value in ("virtual", "bridge"):
        return "virtual"
    if value == "lag":
        return "lag"
    if value.startswith(WIRELESS):
        return "wireless"
    if "base-t" in value:  # 1000base-t, 100base-tx, 10gbase-t...
        return "copper"
    if "base-k" in value or "stackwise" in value:
        return "other"  # backplane, cavi di stack
    if "base-" in value or any(k in value for k in ("sfp", "gbic", "xfp", "cfp", "x2", "xenpak", "osfp", "gfc")):
        return "fiber"
    return "other"


def interface_mode(value: str | None) -> str | None:
    if value == "access":
        return "access"
    if value in ("tagged", "tagged-all", "q-in-q"):
        return "trunk"
    return None


def cable_type(value: str) -> str | None:
    value = (value or "").lower()
    if not value:
        return None
    if value in ("cat5", "cat5e"):
        return "cat5e"
    if value == "cat6":
        return "cat6"
    if value in ("cat6a", "cat7", "cat7a", "cat8"):
        return "cat6a"
    if value.startswith("mmf"):
        return "fiber_mm"
    if value.startswith("smf"):
        return "fiber_sm"
    if value.startswith("dac"):
        return "dac"
    return "other"


def cable_length(length: Any, unit: str | None) -> tuple[float | None, str]:
    try:
        value = float(length)
    except (TypeError, ValueError):
        return None, "m"
    if value <= 0:
        return None, "m"
    factor, unit = {"km": (1000, "m"), "m": (1, "m"), "cm": (1, "cm"), "mi": (5280, "ft"), "ft": (1, "ft"),
                    "in": (1 / 12, "ft")}.get(unit or "m", (1, "m"))
    return round(value * factor, 2), unit


def _color(value: str) -> str | None:
    return f"#{value.lower()}" if re.fullmatch(r"[0-9a-fA-F]{6}", value or "") else None


def _int(value: Any) -> int | None:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _reason(exc: Exception) -> str:
    if isinstance(exc, ValidationError):
        return "; ".join(f"{'.'.join(map(str, e['loc'])) or 'valore'}: {e['msg']}" for e in exc.errors()[:3])
    if isinstance(exc, HTTPException):
        return str(exc.detail)
    if isinstance(exc, (IntegrityError, DataError)):
        return f"valore duplicato o non valido ({str(exc.orig).strip().splitlines()[0][:200]})"
    return str(exc)


class Missing(Exception):
    """Manca un oggetto da cui questo dipende (non importato): va tra i problemi."""


# ---------------------------------------------------------------- scrittura
class Importer:
    def __init__(self, db: Session, snap: Snapshot, site_ids: set[int] | None):
        self.db, self.snap, self.site_ids = db, snap, site_ids
        self.counts = {kind: {"created": 0, "existing": 0, "failed": 0, "skipped": 0} for kind in KINDS}
        self.problems: list[dict] = []
        self.lost_problems = 0
        self.notes: list[str] = []
        self.ids: dict[str, dict[int, int]] = {kind: {} for kind in KINDS}  # id NetBox -> id NetMap
        self.new_devices: set[int] = set()  # device creati da questo import
        self.new_interfaces: set[int] = set()
        self.location_site = {loc["id"]: loc["site"] for loc in snap.locations}
        self.site_names = {s["id"]: s["name"] for s in snap.sites}

    # ----- strumenti
    def problem(self, kind: str, name: Any, message: str) -> None:
        if len(self.problems) < MAX_PROBLEMS:
            self.problems.append({"kind": kind, "name": str(name)[:200], "message": str(message)[:500]})
        else:
            self.lost_problems += 1

    def need(self, kind: str, netbox_id: Any, message: str) -> int:
        found = self.ids[kind].get(netbox_id)
        if found is None:
            raise Missing(message)
        return found

    def create(self, kind: str, name: Any, model: type, schema: type, data: dict, hook=None):
        """Crea un oggetto con gli stessi controlli dei moduli. None (e un problema in elenco) se non va."""
        savepoint = self.db.begin_nested()
        try:
            data = schema(**data).model_dump()
            obj = model()
            apply_data(model, obj, data)
            self.db.add(obj)
            if hook:
                with self.db.no_autoflush:  # i controlli non devono trovare l'oggetto stesso
                    hook(self.db, obj, data, True)
            self.db.flush()
            savepoint.commit()
        except (ValidationError, HTTPException, IntegrityError, DataError, ValueError) as exc:
            savepoint.rollback()
            self.counts[kind]["failed"] += 1
            self.problem(kind, name, _reason(exc))
            return None
        self.counts[kind]["created"] += 1
        return obj

    def sync(self, kind: str, items: list[dict], existing: dict, key: Callable, make: Callable,
             name: Callable[[dict], str] = lambda item: item["name"]) -> None:
        """Per ogni oggetto di NetBox: se in NetMap c'è già (stessa chiave) lo usa, altrimenti lo crea."""
        for item in items:
            try:
                k = key(item)
                if k is None:
                    continue  # fuori dalle sedi scelte
                found = existing.get(k)
                if found is None:
                    obj = self.create(kind, name(item), *make(item))
                    if obj is None:
                        continue
                    found = existing[k] = obj.id
                else:
                    self.counts[kind]["existing"] += 1
            except (Missing, ValueError) as exc:
                self.counts[kind]["failed"] += 1
                self.problem(kind, name(item), str(exc))
                continue
            self.ids[kind][item["id"]] = found

    def site_of_scope(self, scope_type: str | None, scope_id: Any) -> Any:
        """Sede (id NetBox) di un ambito: None = globale, False = sede non letta (fuori da quelle scelte)."""
        if scope_type == "dcim.site":
            return scope_id
        if scope_type == "dcim.location":
            return self.location_site.get(scope_id, False)
        return None

    def wanted(self, netbox_site: Any) -> bool:
        if netbox_site is False:
            return False
        return netbox_site is None or not self.site_ids or netbox_site in self.site_ids

    def site_id(self, netbox_site: Any) -> int | None:
        if netbox_site is None:
            return None
        return self.need("site", netbox_site, f"La sede {self.site_names.get(netbox_site, netbox_site)} non è stata importata")

    # ----- oggetti, nell'ordine delle dipendenze
    def run(self) -> None:
        for step in (self.sites, self.locations, self.racks, self.manufacturers, self.roles, self.device_types,
                     self.vrfs, self.vlans, self.prefixes, self.devices, self.stacks, self.interfaces, self.lags,
                     self.cables, self.ips, self.primary_ips):
            step()

    def sites(self) -> None:
        existing = {name.lower(): id_ for id_, name in self.db.execute(select(Site.id, Site.name))}
        self.sync("site", self.snap.sites, existing, lambda s: s["name"].lower(), lambda s: (
            Site, d.SiteCreate, {"name": s["name"], "address": s["address"] or None,
                                 "description": s["description"] or None, "custom_fields": s["cf"]}))

    def locations(self) -> None:
        existing = {(site, parent, name.lower()): id_ for id_, site, parent, name in
                    self.db.execute(select(Location.id, Location.site_id, Location.parent_id, Location.name))}

        def key(loc):
            parent = self.need("location", loc["parent"], "La posizione che la contiene non è stata importata") if loc["parent"] else None
            return self.site_id(loc["site"]), parent, loc["name"].lower()

        def make(loc):
            site, parent, _ = key(loc)
            return Location, d.LocationCreate, {"name": loc["name"], "site_id": site, "parent_id": parent,
                                                "description": loc["description"] or None,
                                                "custom_fields": loc["cf"]}, rules.location_hook

        self.sync("location", sorted(self.snap.locations, key=lambda loc: (loc["depth"], loc["id"])), existing, key, make)

    def racks(self) -> None:
        existing = {(site, name.lower()): id_ for id_, site, name in self.db.execute(select(Rack.id, Rack.site_id, Rack.name))}

        def make(r):
            height = min(max(_int(r["u_height"]) or 42, 1), 60)
            return Rack, d.RackCreate, {"name": r["name"], "site_id": self.site_id(r["site"]), "u_height": height,
                                        "location_id": self.ids["location"].get(r["location"]),
                                        "description": r["description"] or None, "custom_fields": r["cf"]}, rules.rack_hook

        self.sync("rack", self.snap.racks, existing, lambda r: (self.site_id(r["site"]), r["name"].lower()), make)

    def manufacturers(self) -> None:
        existing = {name.lower(): id_ for id_, name in self.db.execute(select(Manufacturer.id, Manufacturer.name))}
        self.sync("manufacturer", self.snap.manufacturers, existing, lambda m: m["name"].lower(),
                  lambda m: (Manufacturer, d.ManufacturerCreate, {"name": m["name"]}))

    def roles(self) -> None:
        existing = {name.lower(): id_ for id_, name in self.db.execute(select(DeviceRole.id, DeviceRole.name))}

        def make(r):
            level, color = guess_role_style(r["name"])
            return DeviceRole, d.DeviceRoleCreate, {"name": r["name"], "level": level,
                                                    "color": _color(r["color"]) or color,
                                                    "description": r["description"] or None}

        self.sync("device_role", self.snap.roles, existing, lambda r: r["name"].lower(), make)

    def device_types(self) -> None:
        existing = {(maker, model.lower()): id_ for id_, maker, model in
                    self.db.execute(select(DeviceType.id, DeviceType.manufacturer_id, DeviceType.model))}

        def key(t):
            return self.need("manufacturer", t["manufacturer"], "Il produttore non è stato importato"), t["model"].lower()

        def make(t):
            try:
                height = min(max(math.ceil(float(t["u_height"] or 0)), 0), 60)
            except (TypeError, ValueError):
                height = 1
            return DeviceType, d.DeviceTypeCreate, {
                "manufacturer_id": key(t)[0], "model": t["model"], "part_number": t["part_number"] or None,
                "u_height": height, "description": t["description"] or None, "custom_fields": t["cf"]}

        self.sync("device_type", self.snap.device_types, existing, key, make, name=lambda t: t["model"])

    def vrfs(self) -> None:
        by_name = {name.lower(): id_ for id_, name in self.db.execute(select(VRF.id, VRF.name))}
        by_rd = {rd: id_ for id_, rd in self.db.execute(select(VRF.id, VRF.rd).where(VRF.rd.is_not(None)))}
        for v in self.snap.vrfs:
            found = by_name.get(v["name"].lower()) or (by_rd.get(v["rd"]) if v["rd"] else None)
            if found is not None:
                self.counts["vrf"]["existing"] += 1
            else:
                obj = self.create("vrf", v["name"], VRF, i.VRFCreate, {
                    "name": v["name"], "rd": v["rd"] or None, "description": v["description"] or None,
                    "custom_fields": v["cf"]})
                if obj is None:
                    continue
                found = by_name[v["name"].lower()] = obj.id
            self.ids["vrf"][v["id"]] = found

    def vlans(self) -> None:
        groups = {g["id"]: g for g in self.snap.vlan_groups}
        existing = {(site, vid): id_ for id_, site, vid in self.db.execute(select(VLAN.id, VLAN.site_id, VLAN.vid))}

        def netbox_site(v):
            if v["site"]:
                return v["site"]
            group = groups.get(v["group"])
            return self.site_of_scope(group["scope_type"], group["scope_id"]) if group else None

        def key(v):
            site = netbox_site(v)
            return (self.site_id(site), v["vid"]) if self.wanted(site) else None

        def make(v):
            return VLAN, i.VLANCreate, {"vid": v["vid"], "name": v["name"] or str(v["vid"]), "site_id": key(v)[0],
                                        "status": IPAM_STATUS.get(v["status"], "active"),
                                        "description": v["description"] or None, "custom_fields": v["cf"]}, rules.vlan_hook

        self.sync("vlan", self.snap.vlans, existing, key, make, name=lambda v: f"{v['vid']} {v['name']}")

    def prefixes(self) -> None:
        existing = {(vrf, prefix): id_ for id_, vrf, prefix in self.db.execute(select(Prefix.id, Prefix.vrf_id, Prefix.prefix))}
        self.prefix_sites: dict[int, Any] = {}

        def netbox_site(p):
            return p["site"] if p["site"] else self.site_of_scope(p["scope_type"], p["scope_id"])

        def key(p):
            site = netbox_site(p)
            if not self.wanted(site):
                return None
            self.prefix_sites[p["id"]] = site
            vrf = self.need("vrf", p["vrf"], "La VRF non è stata importata") if p["vrf"] else None
            return vrf, normalize_prefix(p["prefix"])

        def make(p):
            vrf, prefix = key(p)
            return Prefix, i.PrefixCreate, {"prefix": prefix, "vrf_id": vrf, "site_id": self.site_id(netbox_site(p)),
                                            "vlan_id": self.ids["vlan"].get(p["vlan"]),
                                            "status": IPAM_STATUS.get(p["status"], "active"),
                                            "description": p["description"] or None, "custom_fields": p["cf"]}, rules.prefix_hook

        self.sync("prefix", self.snap.prefixes, existing, key, make, name=lambda p: p["prefix"])

    def devices(self) -> None:
        chassis = {c["id"]: c for c in self.snap.chassis}
        members: dict[int, list[dict]] = defaultdict(list)
        for x in self.snap.devices:
            if x["vc"]:
                members[x["vc"]].append(x)
        # Stack: un device solo, quello del master (o il primo membro), con il nome dello stack
        self.stack_members: dict[int, list[dict]] = {}
        primary_of: dict[int, int] = {}
        for vc_id, group in members.items():
            group.sort(key=lambda x: (x["vc_position"] is None, x["vc_position"] or 0, x["id"]))
            master = chassis.get(vc_id, {}).get("master")
            primary = next((x for x in group if x["id"] == master), group[0])
            for x in group:
                primary_of[x["id"]] = primary["id"]
            if len(group) > 1:
                self.stack_members[primary["id"]] = group
        self.primary_of = primary_of

        def device_name(x):
            vc = chassis.get(x["vc"]) if x["vc"] else None
            if x["id"] in self.stack_members and vc and vc["name"]:
                return vc["name"]
            return x["name"] or x["display"] or f"device {x['id']}"

        rows = self.db.execute(select(Device.id, Device.site_id, Device.name)).all()
        existing = {(site, name.lower()): id_ for id_, site, name in rows}
        self.device_names = {id_: name for id_, _, name in rows}
        used_tags = {tag: name for tag, name in self.db.execute(select(Device.asset_tag, Device.name).where(Device.asset_tag.is_not(None)))}
        primaries = [x for x in self.snap.devices if primary_of.get(x["id"], x["id"]) == x["id"]]

        def make(x):
            rack = self.ids["rack"].get(x["rack"])
            position = _int(x["position"]) if rack else None
            tag = x["asset_tag"] or None
            if tag and tag in used_tags:
                self.problem("device", device_name(x), f"Asset tag {tag} già usato da {used_tags[tag]}: importato senza")
                tag = None
            return Device, d.DeviceCreate, {
                "name": device_name(x), "site_id": self.site_id(x["site"]),
                "location_id": self.ids["location"].get(x["location"]), "rack_id": rack,
                "rack_position": position if position and 1 <= position <= 60 else None,
                "device_type_id": self.ids["device_type"].get(x["device_type"]),
                "role_id": self.ids["device_role"].get(x["role"]),
                "status": DEVICE_STATUS.get(x["status"], "active"), "serial": x["serial"] or None, "asset_tag": tag,
                "description": x["description"] or None, "custom_fields": x["cf"]}, rules.device_hook

        before = set(existing.values())
        self.sync("device", primaries, existing, lambda x: (self.site_id(x["site"]), device_name(x).lower()), make,
                  name=device_name)
        self.new_devices = set(existing.values()) - before
        for x in primaries:
            if self.ids["device"].get(x["id"]) in self.new_devices:
                self.device_names[self.ids["device"][x["id"]]] = device_name(x)
        for x in self.snap.devices:  # i membri degli stack puntano al device dello stack
            found = self.ids["device"].get(primary_of.get(x["id"], x["id"]))
            if found is not None:
                self.ids["device"][x["id"]] = found

    def stacks(self) -> None:
        for primary_id, group in self.stack_members.items():
            device_id = self.ids["device"].get(primary_id)
            if device_id not in self.new_devices:
                continue
            rack = next(x["rack"] for x in group if x["id"] == primary_id)
            for index, x in enumerate(group, start=1):
                number = x["vc_position"] if isinstance(x["vc_position"], int) and 1 <= x["vc_position"] <= 99 else index
                position = _int(x["position"]) if x["rack"] == rack and rack else None
                self.create("stack_member", f"{self.device_names.get(device_id, '?')} {number}", StackMember,
                            d.StackMemberCreate, {
                                "device_id": device_id, "number": number, "model": x["model"] or None,
                                "serial": x["serial"] or None,
                                "rack_position": position if position and 1 <= position <= 60 else None,
                            }, rules.stack_member_hook)

    def interfaces(self) -> None:
        devices = set(self.ids["device"].values())
        existing = {(dev, name.lower()): id_ for id_, dev, name in
                    self.db.execute(select(Interface.id, Interface.device_id, Interface.name)) if dev in devices}
        for x in self.snap.interfaces:
            device_id = self.ids["device"].get(x["device"])
            label = f"{self.device_names.get(device_id) or x['device_name']} {x['name']}"
            if device_id is None:
                self.counts["interface"]["skipped"] += 1  # device non importato: è già tra i problemi
                continue
            found = existing.get((device_id, x["name"].lower()))
            if found is not None:
                self.counts["interface"]["existing"] += 1
                self.ids["interface"][x["id"]] = found
                continue
            if device_id not in self.new_devices:
                self.counts["interface"]["skipped"] += 1  # device che c'era già: le sue porte restano com'erano
                continue
            mode = interface_mode(x["mode"])
            vlans = self.ids["vlan"]
            try:
                mac = normalize_mac(x["mac"]) if x["mac"] else None
            except ValueError:
                mac = None
            obj = self.create("interface", label, Interface, d.InterfaceCreate, {
                "device_id": device_id, "name": x["name"], "type": interface_type(x["type"]), "enabled": x["enabled"],
                "mgmt_only": x["mgmt_only"], "mac_address": mac,
                "speed_mbps": x["speed"] // 1000 if isinstance(x["speed"], int) and x["speed"] > 0 else None,
                "mtu": x["mtu"] if isinstance(x["mtu"], int) and 64 <= x["mtu"] <= 65535 else None,
                "mode": mode, "untagged_vlan_id": vlans.get(x["untagged"]) if mode else None,
                "tagged_vlan_ids": sorted({vlans[v] for v in x["tagged"] if v in vlans}) if mode == "trunk" else [],
                "description": x["description"] or None, "custom_fields": x["cf"],
            }, rules.interface_hook)
            if obj is not None:
                existing[(device_id, x["name"].lower())] = obj.id
                self.ids["interface"][x["id"]] = obj.id
                self.new_interfaces.add(obj.id)

    def lags(self) -> None:
        for x in self.snap.interfaces:
            iface_id, lag_id = self.ids["interface"].get(x["id"]), self.ids["interface"].get(x["lag"])
            if not x["lag"] or iface_id not in self.new_interfaces or lag_id is None:
                continue
            savepoint = self.db.begin_nested()
            try:
                iface = self.db.get(Interface, iface_id)
                iface.lag_id = lag_id
                rules.interface_hook(self.db, iface, {"lag_id": lag_id}, False)
                self.db.flush()
                savepoint.commit()
            except (HTTPException, IntegrityError, DataError) as exc:
                savepoint.rollback()
                self.problem("interface", f"{x['device_name']} {x['name']}", _reason(exc))

    def cables(self) -> None:
        by_id = {x["id"]: x for x in self.snap.interfaces}
        cables = {c["id"]: c for c in self.snap.cables}
        pairs = {frozenset(p) for p in self.db.execute(select(Cable.a_interface_id, Cable.b_interface_id))}
        seen: set[frozenset] = set()
        skipped = {"circuit": set(), "incomplete": set(), "other_site": set()}
        for x in self.snap.interfaces:
            if not x["cable"]:
                continue
            via: list[str] = []
            if x["peers_type"] == "dcim.interface" and len(x["peers"]) == 1:
                other = x["peers"][0]["id"]
            elif x["peers_type"] in ("dcim.frontport", "dcim.rearport"):
                if x["endpoints_type"] != "dcim.interface" or len(x["endpoints"]) != 1:
                    skipped["incomplete"].add(x["cable"])
                    continue
                other = x["endpoints"][0]
                far = by_id.get(other)
                via = [p["device"] for p in x["peers"][:1]]
                if far and far["peers_type"] in ("dcim.frontport", "dcim.rearport") and far["peers"]:
                    via.append(far["peers"][0]["device"])
            else:
                skipped["circuit"].add(x["cable"])  # circuiti, prese elettriche, console...
                continue
            pair = frozenset((x["id"], other))
            if pair in seen:
                continue
            seen.add(pair)
            far = by_id.get(other)
            if far is None:
                skipped["other_site"].add(x["cable"])
                continue
            label = f"{x['device_name']} {x['name']} ↔ {far['device_name']} {far['name']}"
            a, b = self.ids["interface"].get(x["id"]), self.ids["interface"].get(other)
            if a is None or b is None:
                self.counts["cable"]["skipped"] += 1  # porta non importata (device che c'era già o con errori)
                continue
            if frozenset((a, b)) in pairs:
                self.counts["cable"]["existing"] += 1
                continue
            cable = cables.get(x["cable"]) or {"type": "", "status": None, "label": "", "color": "", "length": None,
                                               "length_unit": None, "description": "", "cf": {}}
            via = list(dict.fromkeys(via))
            if via:
                description = (f"Attraverso il patch panel {via[0]}" if len(via) == 1
                               else f"Attraverso i patch panel {via[0]} e {via[1]}")
                length, unit = None, "m"
            else:
                description = cable["description"] or None
                length, unit = cable_length(cable["length"], cable["length_unit"])
            obj = self.create("cable", label, Cable, d.CableCreate, {
                "a_interface_id": a, "b_interface_id": b, "type": cable_type(cable["type"]),
                "status": CABLE_STATUS.get(cable["status"], "connected"),
                "label": None if via else cable["label"] or None, "color": _color(cable["color"]),
                "length": length, "length_unit": unit, "description": description,
                "custom_fields": {} if via else cable["cf"],
            }, rules.cable_hook)
            if obj is not None:
                pairs.add(frozenset((a, b)))
        self.counts["cable"]["skipped"] += sum(len(ids) for ids in skipped.values())
        parts = [f"{len(skipped['circuit'])} verso circuiti, prese elettriche o console" if skipped["circuit"] else "",
                 f"{len(skipped['incomplete'])} con il percorso incompleto" if skipped["incomplete"] else "",
                 f"{len(skipped['other_site'])} verso device di altre sedi" if skipped["other_site"] else ""]
        if any(parts):
            self.notes.append("Cavi non importati: " + ", ".join(p for p in parts if p))

    def ips(self) -> None:
        interfaces = {x["id"] for x in self.snap.interfaces}
        # Con le sedi scelte: gli IP delle porte lette e quelli liberi dentro le subnet di quelle sedi
        networks: dict[int, set] = defaultdict(set)
        for p in self.snap.prefixes:
            if self.site_ids and self.prefix_sites.get(p["id"]) in self.site_ids:
                try:
                    net = ipaddress.ip_network(p["prefix"], strict=False)
                except ValueError:
                    continue
                networks[net.prefixlen].add(net)

        def inside(address: str) -> bool:
            try:
                ip = ipaddress.ip_interface(address).ip
            except ValueError:
                return False
            return any(ipaddress.ip_network((ip, length), strict=False) in nets
                       for length, nets in networks.items() if length <= ip.max_prefixlen)

        def wanted(x):
            if x["assigned_type"] == "dcim.interface" and x["assigned_id"] in interfaces:
                return True
            return not self.site_ids or (x["assigned_type"] != "dcim.interface" and inside(x["address"]))

        existing = {(vrf, host): id_ for id_, vrf, host in self.db.execute(select(IPAddress.id, IPAddress.vrf_id, IPAddress.host))}

        def key(x):
            if not wanted(x):
                return None
            vrf = self.need("vrf", x["vrf"], "La VRF non è stata importata") if x["vrf"] else None
            return vrf, str(ipaddress.ip_interface(normalize_ip_interface(x["address"])).ip)

        def make(x):
            interface = self.ids["interface"].get(x["assigned_id"]) if x["assigned_type"] == "dcim.interface" else None
            return IPAddress, i.IPAddressCreate, {
                "address": x["address"], "vrf_id": key(x)[0], "interface_id": interface,
                "status": IP_STATUS.get(x["status"], "active"), "dns_name": x["dns_name"] or None,
                "description": x["description"] or None, "custom_fields": x["cf"]}, rules.ip_hook

        self.sync("ip", self.snap.ips, existing, key, make, name=lambda x: x["address"])

    def primary_ips(self) -> None:
        """IP di management dei device creati adesso: il primary IP di NetBox (dello stack: del master)."""
        done: set[int] = set()
        ordered = sorted(self.snap.devices, key=lambda x: self.primary_of.get(x["id"], x["id"]) != x["id"])
        for x in ordered:
            device_id = self.ids["device"].get(x["id"])
            if device_id not in self.new_devices or device_id in done:
                continue
            for ref in (x["primary_ip4"], x["primary_ip6"]):
                ip = self.db.get(IPAddress, self.ids["ip"].get(ref)) if self.ids["ip"].get(ref) else None
                if ip is None or ip.interface is None or ip.interface.device_id != device_id:
                    continue
                savepoint = self.db.begin_nested()
                try:
                    ip.is_primary = True
                    rules.ip_hook(self.db, ip, {}, False)
                    self.db.flush()
                    savepoint.commit()
                    done.add(device_id)
                    break
                except (HTTPException, IntegrityError) as exc:
                    savepoint.rollback()
                    self.problem("ip", ip.address, _reason(exc))

    def summary(self) -> str:
        total = {key: sum(c[key] for c in self.counts.values()) for key in ("created", "existing", "failed")}
        return f"{total['created']} oggetti creati, {total['existing']} già presenti, {total['failed']} non importati"


# ---------------------------------------------------------------- esecuzione (worker)
class RunLog:
    def __init__(self, run: ImportRun):
        self.run = run
        self.lines: list[str] = [run.log] if run.log else []

    def __call__(self, message: str) -> None:
        stamp = datetime.now().astimezone().strftime("%H:%M:%S")  # ora locale del container (variabile TZ)
        self.lines.append(f"{stamp} {message}\n")
        self.run.log = "".join(self.lines)


def execute_import(db: Session, run_id: int, client_factory: Callable[..., Client] = Client) -> ImportRun:
    run = db.get(ImportRun, run_id)
    run.status, run.started_at = RunStatus.RUNNING.value, run.started_at or now()
    log = RunLog(run)
    try:
        try:
            token = decrypt(run.token_enc) if run.token_enc else ""
        except SecretError as exc:
            raise NetBoxError("Il token non si legge più (chiave dei segreti cambiata): rilancia l'import") from exc
        if not token:
            raise NetBoxError("Manca il token: rilancia l'import dalla pagina")
        client = client_factory(run.url, token, run.verify_tls)
        run.netbox_version = client.version()
        log(f"Connessione a NetBox {run.netbox_version}")
        db.commit()

        def progress(message: str) -> None:
            log(message)
            db.commit()

        site_ids = set(run.site_ids or []) or None
        snap = fetch(client, site_ids, progress)
        if site_ids:
            run.site_names = sorted(s["name"] for s in snap.sites)
            missing = site_ids - {s["id"] for s in snap.sites}
            if missing:
                raise NetBoxError(f"Sedi non trovate in NetBox: {', '.join(map(str, sorted(missing)))}")
        log("Simulazione: scrittura di prova nel database…" if run.dry_run else "Scrittura nel database…")
        db.commit()

        db.info["audit_source"] = "netbox"  # storico delle modifiche
        if run.requested_by_id:
            db.info["audit_user"] = (run.requested_by_id, run.requested_by)
        importer = Importer(db, snap, site_ids)
        importer.run()
        if run.dry_run:
            db.rollback()  # la simulazione non lascia niente (neanche lo storico)
        else:
            db.commit()
        run.counts, run.problems = importer.counts, importer.problems
        for note in importer.notes:
            log(note)
        if importer.lost_problems:
            log(f"Altri {importer.lost_problems} problemi non elencati")
        log(("Fine della simulazione (niente è stato salvato): " if run.dry_run else "Fine: ") + importer.summary())
        run.status = RunStatus.DONE.value
    except NetBoxError as exc:
        db.rollback()
        run.status = RunStatus.FAILED.value
        log(f"Import non eseguito: {exc}")
    except Exception as exc:
        db.rollback()
        logger.exception("Import da NetBox %s fallito", run_id)
        run.status = RunStatus.FAILED.value
        log(f"Errore inatteso: {exc}")
    finally:
        db.info.pop("audit_source", None)
        db.info.pop("audit_user", None)
    run.log = "".join(log.lines)
    run.token_enc = None  # il token serve solo per questo import
    run.finished_at = now()
    db.commit()
    return run


def active_run(db: Session) -> ImportRun | None:
    return db.scalars(select(ImportRun).where(
        ImportRun.status.in_([RunStatus.QUEUED.value, RunStatus.RUNNING.value]))).first()


def prune(db: Session) -> None:
    """Tiene gli ultimi KEEP_RUNS import (con log e problemi)."""
    old = db.scalars(select(ImportRun).order_by(ImportRun.id.desc()).offset(KEEP_RUNS)).all()
    for run in old:
        db.delete(run)


def claim_next(db: Session) -> int | None:
    run = db.scalars(
        select(ImportRun).where(ImportRun.status == RunStatus.QUEUED.value).order_by(ImportRun.id).limit(1)
        .with_for_update(skip_locked=True)
    ).first()
    if run is None:
        db.rollback()
        return None
    run.status, run.started_at = RunStatus.RUNNING.value, now()
    db.commit()
    return run.id


def recover_interrupted(db: Session) -> int:
    runs = list(db.scalars(select(ImportRun).where(ImportRun.status == RunStatus.RUNNING.value)))
    for run in runs:
        RunLog(run)("Interrotto: il worker è stato riavviato durante l'import (niente è stato salvato)")
        run.status, run.finished_at, run.token_enc = RunStatus.FAILED.value, now(), None
    db.commit()
    return len(runs)


def import_loop(session_factory) -> None:
    """Thread del worker: prende gli import in coda (uno alla volta)."""
    recovered = False
    while True:
        try:
            with session_factory() as db:
                if not recovered:
                    if count := recover_interrupted(db):
                        logger.warning("%s import da NetBox interrotti segnati come falliti", count)
                    recovered = True
                run_id = claim_next(db)
            if run_id is not None:
                logger.info("Import da NetBox %s avviato", run_id)
                with session_factory() as db:
                    run = execute_import(db, run_id)
                    logger.info("Import da NetBox %s finito: %s", run_id, run.status)
                continue
        except (OperationalError, ProgrammingError):
            time.sleep(30)  # database non pronto o migration non ancora applicata
            continue
        except Exception:
            logger.exception("Errore inatteso negli import da NetBox")
        time.sleep(POLL_SECONDS)
