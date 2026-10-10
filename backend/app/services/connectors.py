"""Import da altri programmi: Zabbix, LibreNMS, Observium, PRTG, GLPI, Lansweeper.

Ogni connettore legge dalla sua API e traduce in uno Snapshot come quello di NetBox (services/netbox.py): poi
l'import è lo stesso (Importer), con simulazione, log, problemi, storico e "crea solo quello che manca".

Questi programmi non hanno sedi, posizioni e cavi come NetBox: ogni connettore dice da dove li prende (es. le
posizioni di LibreNMS diventano sedi, la sonda di PRTG è la sede); i device senza sede vanno nella sede predefinita
scelta nella pagina. L'IP di management va su una porta "mgmt" quando la sorgente non dice su quale porta sta.

Interfaccia di un connettore: label, version(), probe() -> {version, counts, groups: [{id, name, devices}]},
fetch(group_ids, progress, default_site) -> Snapshot, group_names(snap, group_ids), close().
"""
import base64
import ipaddress
import itertools
import json
import re
import ssl
import urllib.error
import urllib.request
from collections import Counter
from collections.abc import Callable
from dataclasses import fields
from typing import Any
from urllib.parse import urlencode, urlsplit

from app.discovery.vendors import vendor_name
from app.services.netbox import Snapshot, SourceError

TIMEOUT = 60
PAGE = 500


def normalize_url(url: str, label: str) -> str:
    url = (url or "").strip().rstrip("/")
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        raise SourceError(f"Indirizzo di {label} non valido: serve http:// o https:// seguito dal nome del server")
    return url


def _text(value: Any, limit: int | None = None) -> str:
    if value is None or isinstance(value, (dict, list)):
        return ""
    text = str(value).strip()
    return text[:limit] if limit else text


def _dropdown(value: Any) -> str:
    """Valore di un menu di GLPI con expand_dropdowns: vuoto se non scelto (0, "0", "&nbsp;")."""
    text = _text(value)
    return "" if text in ("0", "&nbsp;") else text


def _ip(value: Any) -> str | None:
    """L'indirizzo se è un IP (non un nome DNS), altrimenti None."""
    try:
        return str(ipaddress.ip_address(_text(value).split("/")[0]))
    except ValueError:
        return None


class HttpSource:
    """Richieste HTTP con errori chiari per l'utente (come il client di NetBox)."""

    key = label = ""
    group_label = ""

    def __init__(self, verify_tls: bool):
        self.context = ssl.create_default_context()
        if not verify_tls:
            self.context.check_hostname = False
            self.context.verify_mode = ssl.CERT_NONE

    def http(self, url: str, headers: dict | None = None, data: bytes | None = None,
             method: str | None = None) -> tuple[bytes, dict]:
        request = urllib.request.Request(url, data=data, method=method,
                                         headers={"Accept": "application/json", "User-Agent": "NetMap", **(headers or {})})
        path = urlsplit(url).path or "/"
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT, context=self.context) as response:
                return response.read(), dict(response.headers)
        except urllib.error.HTTPError as exc:
            if exc.code in (401, 403):
                raise SourceError(f"{self.label} rifiuta le credenziali ({exc.code}): controlla che siano giuste, "
                                  "non scadute e con il permesso di lettura") from exc
            if exc.code == 404:
                raise SourceError(f"{self.label} non trova {path}: l'indirizzo è giusto?") from exc
            raise SourceError(f"{self.label} ha risposto {exc.code} su {path}") from exc
        except urllib.error.URLError as exc:
            if isinstance(exc.reason, ssl.SSLCertVerificationError):
                raise SourceError(f"Il certificato HTTPS di {self.label} non è valido ({exc.reason.verify_message}): "
                                  "usa il nome giusto del server o togli la verifica del certificato") from exc
            raise SourceError(f"{self.label} non risponde ({exc.reason})") from exc
        except OSError as exc:
            raise SourceError(f"{self.label} non risponde ({exc})") from exc

    def json(self, url: str, headers: dict | None = None, data: bytes | None = None, method: str | None = None) -> Any:
        body, _ = self.http(url, headers, data, method)
        return self.parse(body)

    def parse(self, body: bytes) -> Any:
        try:
            return json.loads(body or b"null")
        except ValueError as exc:
            raise SourceError(f"La risposta non è JSON: l'indirizzo è quello di {self.label}?") from exc

    def group_names(self, snap: Snapshot, group_ids: set) -> list[str]:
        return sorted(self.chosen_names)

    def close(self) -> None:
        pass


# ---------------------------------------------------------------- costruzione dello Snapshot
ROLE_NAMES = {  # tipi di LibreNMS e Observium
    "network": "Rete", "server": "Server", "wireless": "Wireless", "firewall": "Firewall", "power": "Alimentazione",
    "printer": "Stampante", "storage": "Storage", "appliance": "Appliance", "environment": "Ambiente",
    "loadbalancer": "Bilanciatore", "collaboration": "Collaborazione", "workstation": "Workstation",
    "security": "Sicurezza", "video": "Video", "voip": "VoIP",
}

IF_TYPES = {  # ifType IANA per nome, come discovery/matching.py
    "ethernetcsmacd": "copper", "gigabitethernet": "copper", "fastether": "copper", "fastetherfx": "fiber",
    "ieee80211": "wireless", "ieee8023adlag": "lag", "softwareloopback": "virtual", "propvirtual": "virtual",
    "tunnel": "virtual", "l2vlan": "virtual", "l3ipvlan": "virtual", "bridge": "virtual",
}


class Builder:
    """Snapshot da sorgenti "piatte": id finti, sedi, posizioni, produttori e ruoli riusati per nome."""

    def __init__(self, default_site: str):
        self.default_site = _text(default_site, 100) or "Importati"
        self.snap = Snapshot(**{f.name: [] for f in fields(Snapshot)})
        self._next = itertools.count(1)
        self._sites: dict[str, int] = {}
        self._locations: dict[tuple, int] = {}
        self._makers: dict[str, int] = {}
        self._roles: dict[str, int] = {}
        self._types: dict[tuple, int] = {}
        self.devices: dict[int, dict] = {}
        self.interfaces: dict[int, dict] = {}
        self.device_ips: dict[int, list[tuple[str, int]]] = {}  # device -> [(ip, porta)]

    def _common(self, description: str = "", cf: dict | None = None) -> dict:
        return {"id": next(self._next), "description": _text(description), "cf": cf or {}}

    def site(self, name: Any = None) -> int:
        name = _text(name, 100) or self.default_site
        if name.lower() not in self._sites:
            item = {**self._common(), "name": name, "address": ""}
            self.snap.sites.append(item)
            self._sites[name.lower()] = item["id"]
        return self._sites[name.lower()]

    def location(self, site: int, path: list[Any]) -> int | None:
        parent, depth = None, 0
        for part in path:
            name = _text(part, 100)
            if not name:
                continue
            key = (site, parent, name.lower())
            if key not in self._locations:
                item = {**self._common(), "name": name, "site": site, "parent": parent, "depth": depth}
                self.snap.locations.append(item)
                self._locations[key] = item["id"]
            parent, depth = self._locations[key], depth + 1
        return parent

    def manufacturer(self, name: Any) -> int | None:
        name = _text(name, 100)
        if not name:
            return None
        if name.lower() not in self._makers:
            item = {"id": next(self._next), "name": name}
            self.snap.manufacturers.append(item)
            self._makers[name.lower()] = item["id"]
        return self._makers[name.lower()]

    def role(self, name: Any) -> int | None:
        name = _text(name, 100)
        if not name:
            return None
        if name.lower() not in self._roles:
            item = {**self._common(), "name": name, "color": ""}
            self.snap.roles.append(item)
            self._roles[name.lower()] = item["id"]
        return self._roles[name.lower()]

    def device_type(self, maker: Any, model: Any) -> int | None:
        maker_id, model = self.manufacturer(maker), _text(model, 100)
        if maker_id is None or not model:
            return None
        key = (maker_id, model.lower())
        if key not in self._types:
            item = {**self._common(), "manufacturer": maker_id, "model": model, "part_number": "", "u_height": 1}
            self.snap.device_types.append(item)
            self._types[key] = item["id"]
        return self._types[key]

    def device(self, name: Any, site: int, *, location: int | None = None, role: int | None = None,
               device_type: int | None = None, status: str = "active", serial: Any = "", asset_tag: Any = "",
               description: Any = "", cf: dict | None = None) -> int:
        name = _text(name, 100) or "senza nome"
        item = {**self._common(description, cf), "name": name, "display": name, "site": site, "location": location,
                "rack": None, "position": None, "device_type": device_type, "model": "", "role": role,
                "status": status, "serial": _text(serial, 100), "asset_tag": _text(asset_tag, 100),
                "primary_ip4": None, "primary_ip6": None, "vc": None, "vc_position": None}
        self.snap.devices.append(item)
        self.devices[item["id"]] = item
        return item["id"]

    def interface(self, device: int, name: Any, *, type: str = "other", mac: Any = None, speed_mbps: Any = None,
                  mtu: Any = None, enabled: bool = True, description: Any = "", mgmt_only: bool = False) -> int:
        speed = int(speed_mbps) if isinstance(speed_mbps, (int, float)) and speed_mbps > 0 else None
        item = {**self._common(description), "device": device, "device_name": self.devices[device]["name"],
                "name": _text(name, 100) or "?", "type": type, "enabled": enabled, "mgmt_only": mgmt_only,
                "mac": _text(mac) or None, "speed": speed * 1000 if speed else None,  # NetBox: kbps
                "mtu": int(mtu) if str(mtu or "").isdigit() else None, "mode": None, "untagged": None, "tagged": [],
                "lag": None, "cable": None, "peers_type": None, "peers": [], "endpoints_type": None, "endpoints": []}
        self.snap.interfaces.append(item)
        self.interfaces[item["id"]] = item
        return item["id"]

    def ip(self, address: Any, interface: int | None = None, dns_name: Any = "") -> int | None:
        text = _text(address)
        try:
            host = ipaddress.ip_interface(text)
        except ValueError:
            return None
        item = {**self._common(), "address": text, "vrf": None, "status": "active", "dns_name": _text(dns_name, 255),
                "assigned_type": "dcim.interface" if interface else None, "assigned_id": interface}
        self.snap.ips.append(item)
        if interface:
            device = self.interfaces[interface]["device"]
            self.device_ips.setdefault(device, []).append((str(host.ip), item["id"]))
        return item["id"]

    def management_ip(self, device: int, address: Any, mac: Any = None, dns_name: Any = "") -> None:
        """IP di management: quello della porta che già ce l'ha, altrimenti su una porta "mgmt"."""
        host = _ip(address)
        if host is None:
            return
        ip_id = next((ip_id for ip, ip_id in self.device_ips.get(device, []) if ip == host), None)
        if ip_id is None:
            port = self.interface(device, "mgmt", type="virtual", mac=mac, mgmt_only=True)
            ip_id = self.ip(host, port, dns_name)
        key = "primary_ip6" if ":" in host else "primary_ip4"
        self.devices[device][key] = ip_id

    def cable(self, a: int, b: int) -> None:
        first, second = self.interfaces.get(a), self.interfaces.get(b)
        if not first or not second or a == b or first["cable"] or second["cable"]:
            return
        item = {**self._common(), "type": "", "status": "connected", "label": "", "color": "", "length": None,
                "length_unit": None}
        self.snap.cables.append(item)
        for this, other in ((first, second), (second, first)):
            this.update(cable=item["id"], peers_type="dcim.interface",
                        peers=[{"id": other["id"], "device": other["device_name"]}])


# ---------------------------------------------------------------- Zabbix
class Zabbix(HttpSource):
    """API JSON-RPC (api_jsonrpc.php). Token API (5.4+) oppure utente e password. Gruppi di host da scegliere;
    tutti i device nella sede predefinita, la posizione dall'inventario."""

    key, label, group_label = "zabbix", "Zabbix", "gruppi di host"
    INVENTORY = ["type", "serialno_a", "asset_tag", "vendor", "model", "hardware", "location", "macaddress_a"]

    def __init__(self, url: str, secrets: dict, username: str | None, verify_tls: bool):
        super().__init__(verify_tls)
        base = normalize_url(url, self.label)
        self.endpoint = base if base.endswith("api_jsonrpc.php") else f"{base}/api_jsonrpc.php"
        self.token, self.username = secrets.get("token") or "", (username or "").strip()
        self._version: str | None = None
        self._session: str | None = None
        self.chosen_names: list[str] = []

    def call(self, method: str, params: Any, auth: bool = True) -> Any:
        body: dict = {"jsonrpc": "2.0", "method": method, "params": params, "id": 1}
        headers = {"Content-Type": "application/json-rpc"}
        if auth:
            session = self.session()
            if self.numbers >= (6, 4):
                headers["Authorization"] = f"Bearer {session}"
            else:
                body["auth"] = session
        data = self.json(self.endpoint, headers, json.dumps(body).encode())
        if not isinstance(data, dict):
            raise SourceError("Risposta inattesa: l'indirizzo è quello di Zabbix?")
        if data.get("error"):
            error = data["error"]
            message = _text(error.get("data")) or _text(error.get("message"))
            if re.search(r"not author|session|name or password|re-login|api token", message, re.IGNORECASE):
                raise SourceError(f"Zabbix rifiuta le credenziali: {message}")
            raise SourceError(f"Zabbix ha risposto con un errore: {message}")
        return data.get("result")

    @property
    def numbers(self) -> tuple[int, ...]:
        return tuple(int(n) for n in re.findall(r"\d+", self.version())[:2])

    def version(self) -> str:
        if self._version is None:
            self._version = _text(self.call("apiinfo.version", {}, auth=False)) or "?"
        return self._version

    def session(self) -> str:
        if self._session is None:
            if self.username:
                key = "username" if self.numbers >= (5, 4) else "user"
                self._session = _text(self.call("user.login", {key: self.username, "password": self.token}, auth=False))
            else:
                self._session = self.token
        return self._session

    def close(self) -> None:
        if self.username and self._session:
            try:
                self.call("user.logout", [])
            except SourceError:
                pass

    def _groups_param(self) -> tuple[str, str]:
        return ("selectHostGroups", "hostgroups") if self.numbers >= (6, 2) else ("selectGroups", "groups")

    def hosts(self, group_ids: set | None = None, full: bool = True) -> list[dict]:
        select_groups, _ = self._groups_param()
        params: dict = {"output": ["hostid", "host", "name", "status", "description"] if full else ["hostid"],
                        select_groups: ["groupid", "name"]}
        if full:
            params.update(selectInterfaces=["ip", "dns", "useip", "type", "main"], selectInventory=self.INVENTORY)
        if group_ids:
            params["groupids"] = sorted(str(g) for g in group_ids)
        return self.call("host.get", params) or []

    def probe(self) -> dict:
        version = self.version()
        _, groups_key = self._groups_param()
        hosts = self.hosts(full=False)
        per_group = Counter((g["groupid"], g["name"]) for h in hosts for g in h.get(groups_key) or [])
        groups = [{"id": gid, "name": name, "devices": n} for (gid, name), n in per_group.items()]
        return {"version": version, "counts": {"devices": len(hosts), "groups": len(groups)},
                "groups": sorted(groups, key=lambda g: g["name"].lower())}

    def fetch(self, group_ids: set | None, progress: Callable[[str], None], default_site: str) -> Snapshot:
        _, groups_key = self._groups_param()
        hosts = self.hosts(group_ids)
        progress(f"Letti da Zabbix: {len(hosts)} host")
        if group_ids:
            wanted = {str(g) for g in group_ids}
            self.chosen_names = sorted({g["name"] for h in hosts for g in h.get(groups_key) or [] if g["groupid"] in wanted})
        b = Builder(default_site)
        site = b.site()
        for h in hosts:
            inventory = h.get("inventory") if isinstance(h.get("inventory"), dict) else {}  # [] se spento
            device = b.device(
                h.get("name") or h.get("host"), site, location=b.location(site, [inventory.get("location")]),
                role=b.role(inventory.get("type")), device_type=b.device_type(inventory.get("vendor"), inventory.get("model")),
                status="active" if str(h.get("status")) == "0" else "offline", serial=inventory.get("serialno_a"),
                asset_tag=inventory.get("asset_tag"), description=h.get("description"),
                cf={"zabbix_host": h["host"]} if h.get("host") and h.get("host") != h.get("name") else None)
            interfaces = h.get("interfaces") or []
            # Prima SNMP (2), poi l'agente (1), poi le altre; la principale prima
            interfaces.sort(key=lambda i: ({"2": 0, "1": 1}.get(str(i.get("type")), 2), str(i.get("main")) != "1"))
            for i in interfaces:
                address = i.get("ip") if str(i.get("useip")) == "1" else i.get("dns")
                if _ip(address) or _ip(i.get("ip")):
                    b.management_ip(device, _ip(address) or i.get("ip"), inventory.get("macaddress_a"), i.get("dns"))
                    break
        return b.snap


# ---------------------------------------------------------------- LibreNMS e Observium
class LibreNMS(HttpSource):
    """API REST /api/v0 con un token (X-Auth-Token). Le posizioni di LibreNMS diventano sedi (si sceglie quali);
    porte, IP e vicini LLDP/CDP (cavi tra i device importati)."""

    key, label, group_label = "librenms", "LibreNMS", "posizioni"
    NO_LOCATION = 0

    def __init__(self, url: str, secrets: dict, username: str | None, verify_tls: bool):
        super().__init__(verify_tls)
        base = normalize_url(url, self.label)
        self.base = base[:-len("/api/v0")] if base.endswith("/api/v0") else base
        self.token, self.username = secrets.get("token") or "", (username or "").strip()
        self.chosen_names: list[str] = []
        self.notes: list[str] = []

    def headers(self) -> dict:
        return {"X-Auth-Token": self.token}

    def get(self, path: str, params: dict | None = None) -> Any:
        url = f"{self.base}/api/v0/{path}" + (f"?{urlencode(params)}" if params else "")
        data = self.json(url, self.headers())
        if isinstance(data, dict) and data.get("status") == "error":
            raise SourceError(f"{self.label} ha risposto con un errore: {_text(data.get('message'))}")
        return data

    def items(self, data: Any, key: str) -> list[dict]:
        value = data.get(key) if isinstance(data, dict) else None
        if isinstance(value, dict):  # Observium: {"id": {...}}
            value = list(value.values())
        if not isinstance(value, list):
            raise SourceError(f"Risposta inattesa da {self.label} ({key}): l'indirizzo è giusto?")
        return [v for v in value if isinstance(v, dict)]

    def version(self) -> str:
        system = self.get("system").get("system")
        first = system[0] if isinstance(system, list) and system else system if isinstance(system, dict) else {}
        return _text(first.get("local_ver")) or "?"

    def devices(self) -> list[dict]:
        return self.items(self.get("devices", {"type": "all"}), "devices")

    def location_of(self, x: dict) -> tuple[Any, str]:
        name = _text(x.get("location"), 100)
        return (x.get("location_id") or name or self.NO_LOCATION), name

    def probe(self) -> dict:
        version = self.version()
        devices = self.devices()
        per_location = Counter(self.location_of(x) for x in devices)
        groups = [{"id": lid, "name": name or "(senza posizione)", "devices": n} for (lid, name), n in per_location.items()]
        return {"version": version, "counts": {"devices": len(devices), "groups": len(groups)},
                "groups": sorted(groups, key=lambda g: g["name"].lower())}

    def optional(self, path: str, key: str, params: dict | None = None, what: str = "") -> list[dict]:
        """Elenco che può mancare (versione vecchia o permessi): si va avanti senza, con una nota nel log."""
        try:
            return self.items(self.get(path, params), key)
        except SourceError as exc:
            self.notes.append(f"{what} non letti da {self.label}: {exc}")
            return []

    def ports(self) -> list[dict]:
        columns = "port_id,device_id,ifName,ifDescr,ifAlias,ifPhysAddress,ifSpeed,ifType,ifAdminStatus,ifMtu,deleted"
        return self.optional("ports", "ports", {"columns": columns}, "Porte")

    def addresses(self) -> list[dict]:
        return self.optional("resources/ip/addresses", "ip_addresses", what="Indirizzi IP")

    def links(self) -> list[dict]:
        return self.optional("resources/links", "links", what="Vicini LLDP/CDP")

    def maker_and_model(self, x: dict) -> tuple[str, str]:
        maker = _text(x.get("vendor")) or vendor_name(_text(x.get("sysObjectID")).lstrip("."))
        if maker == "Sconosciuto" or maker.startswith("Enterprise "):
            maker = ""
        return maker, _text(x.get("hardware"))

    def fetch(self, group_ids: set | None, progress: Callable[[str], None], default_site: str) -> Snapshot:
        devices = self.devices()
        if group_ids:
            wanted = {str(g) for g in group_ids}
            devices = [x for x in devices if str(self.location_of(x)[0]) in wanted]
            self.chosen_names = sorted({self.location_of(x)[1] or "(senza posizione)" for x in devices})
        progress(f"Letti da {self.label}: {len(devices)} device")
        ports, addresses, links = self.ports(), self.addresses(), self.links()
        progress(f"Letti da {self.label}: {len(ports)} porte, {len(addresses)} indirizzi IP, {len(links)} vicini")
        for note in self.notes:
            progress(note)

        b = Builder(default_site)
        devices_by_id: dict[str, int] = {}
        for x in devices:
            maker, model = self.maker_and_model(x)
            name = x.get("display") or x.get("sysName") or x.get("hostname")
            disabled = str(x.get("disabled") or "0") not in ("0", "false", "False")
            devices_by_id[str(x.get("device_id"))] = b.device(
                name, b.site(self.location_of(x)[1]), role=b.role(ROLE_NAMES.get(_text(x.get("type")).lower())),
                device_type=b.device_type(maker, model), status="offline" if disabled else "active",
                serial=x.get("serial"), description=x.get("purpose"),
                cf={k: v for k, v in (("os", _text(x.get("os"))), ("os_version", _text(x.get("version")))) if v})
        ports_by_id: dict[str, int] = {}
        for p in ports:
            device = devices_by_id.get(str(p.get("device_id")))
            if device is None or str(p.get("deleted") or "0") not in ("0", "false", "False"):
                continue
            name = _text(p.get("ifName")) or _text(p.get("ifDescr"))
            alias = _text(p.get("ifAlias"))
            speed = p.get("ifSpeed")
            ports_by_id[str(p.get("port_id"))] = b.interface(
                device, name, type=IF_TYPES.get(_text(p.get("ifType")).lower(), "other"), mac=p.get("ifPhysAddress"),
                speed_mbps=int(speed) // 1_000_000 if str(speed or "").isdigit() else None, mtu=p.get("ifMtu"),
                enabled=_text(p.get("ifAdminStatus")).lower() != "down", description="" if alias == name else alias)
        for a in addresses:
            port = ports_by_id.get(str(a.get("port_id")))
            address = a.get("ipv4_address") or a.get("ipv6_address")
            prefix = a.get("ipv4_prefixlen") or a.get("ipv6_prefixlen")
            if port and address:
                b.ip(f"{address}/{prefix}" if prefix else address, port)
        for x in devices:
            device = devices_by_id[str(x.get("device_id"))]
            b.management_ip(device, x.get("ip") or x.get("hostname"))
        for link in links:
            local, remote = ports_by_id.get(str(link.get("local_port_id"))), ports_by_id.get(str(link.get("remote_port_id")))
            if local and remote:
                b.cable(local, remote)
        return b.snap


class Observium(LibreNMS):
    """API /api/v0 di Observium (edizioni Professional ed Enterprise) con utente e password. Come LibreNMS, senza
    indirizzi IP e vicini (l'IP di management va su una porta "mgmt")."""

    key, label = "observium", "Observium"

    def headers(self) -> dict:
        credentials = base64.b64encode(f"{self.username}:{self.token}".encode()).decode()
        return {"Authorization": f"Basic {credentials}"}

    def get(self, path: str, params: dict | None = None) -> Any:
        return super().get(f"{path}/", params)

    def version(self) -> str:
        self.devices()  # niente endpoint della versione: basta che risponda
        return "API v0"

    def devices(self) -> list[dict]:
        return self.items(self.get("devices"), "devices")

    def ports(self) -> list[dict]:
        return self.optional("ports", "ports", what="Porte")

    def addresses(self) -> list[dict]:
        return []

    def links(self) -> list[dict]:
        return []


# ---------------------------------------------------------------- PRTG
class PRTG(HttpSource):
    """API di PRTG (table.json): chiave API, oppure utente con password o passhash. La sonda (probe) è la sede, il
    gruppo la posizione; l'indirizzo del device, se è un IP, quello di management."""

    key, label, group_label = "prtg", "PRTG", "sonde"
    COLUMNS = "objid,device,host,group,probe,tags,active"

    def __init__(self, url: str, secrets: dict, username: str | None, verify_tls: bool):
        super().__init__(verify_tls)
        self.base = normalize_url(url, self.label)
        token, username = secrets.get("token") or "", (username or "").strip()
        if username:
            self.auth = {"username": username, ("passhash" if token.isdigit() else "password"): token}
        else:
            self.auth = {"apitoken": token}
        self.chosen_names: list[str] = []

    def get(self, path: str, params: dict | None = None) -> Any:
        data = self.json(f"{self.base}/api/{path}?{urlencode({**(params or {}), **self.auth})}")
        if not isinstance(data, dict):
            raise SourceError("Risposta inattesa: l'indirizzo è quello di PRTG?")
        return data

    def version(self) -> str:
        return _text(self.get("status.json").get("Version")) or "?"

    def devices(self) -> list[dict]:
        data = self.get("table.json", {"content": "devices", "columns": self.COLUMNS, "count": 50000})
        return [x for x in data.get("devices") or [] if isinstance(x, dict)]

    def probe(self) -> dict:
        version = self.version()
        devices = self.devices()
        per_probe = Counter(_text(x.get("probe")) for x in devices)
        groups = [{"id": name, "name": name or "(senza sonda)", "devices": n} for name, n in per_probe.items()]
        return {"version": version, "counts": {"devices": len(devices), "groups": len(groups)},
                "groups": sorted(groups, key=lambda g: g["name"].lower())}

    def fetch(self, group_ids: set | None, progress: Callable[[str], None], default_site: str) -> Snapshot:
        devices = self.devices()
        if group_ids:
            devices = [x for x in devices if _text(x.get("probe")) in {str(g) for g in group_ids}]
            self.chosen_names = sorted({_text(x.get("probe")) or "(senza sonda)" for x in devices})
        progress(f"Letti da PRTG: {len(devices)} device")
        b = Builder(default_site)
        for x in devices:
            probe, group = _text(x.get("probe")), _text(x.get("group"))
            site = b.site(probe)
            active = x.get("active_raw", x.get("active"))
            host = _text(x.get("host"))
            device = b.device(
                x.get("device"), site, location=b.location(site, [group] if group and group != probe else []),
                status="offline" if active in (False, 0, "0", "false") else "active",
                description="" if _ip(host) else (f"Host: {host}" if host else ""),
                cf={"prtg_tags": _text(x.get("tags"))} if _text(x.get("tags")) else None)
            b.management_ip(device, host)
        return b.snap


# ---------------------------------------------------------------- GLPI
class GLPI(HttpSource):
    """API REST di GLPI (apirest.php) con il token dell'utente (e l'App-Token se il client API lo chiede), oppure
    utente e password. Apparati di rete con porte, IP e collegamenti tra porte; il primo livello della posizione è
    la sede, il resto la posizione."""

    key, label, group_label = "glpi", "GLPI", "sedi (primo livello delle posizioni)"
    PORT_TYPES = {"networkportethernet": "copper", "networkportfiberchannel": "fiber", "networkportwifi": "wireless",
                  "networkportaggregate": "lag", "networkportalias": "virtual", "networkportlocal": "virtual"}

    def __init__(self, url: str, secrets: dict, username: str | None, verify_tls: bool):
        super().__init__(verify_tls)
        base = normalize_url(url, self.label)
        self.base = base if base.endswith("apirest.php") else f"{base}/apirest.php"
        self.token, self.app_token = secrets.get("token") or "", secrets.get("app_token") or ""
        self.username = (username or "").strip()
        self._session: str | None = None
        self.chosen_names: list[str] = []
        self.notes: list[str] = []

    def headers(self) -> dict:
        headers = {"Content-Type": "application/json"}
        if self.app_token:
            headers["App-Token"] = self.app_token
        if self._session:
            headers["Session-Token"] = self._session
        return headers

    def session(self) -> None:
        if self._session:
            return
        if self.username:
            auth = "Basic " + base64.b64encode(f"{self.username}:{self.token}".encode()).decode()
        else:
            auth = f"user_token {self.token}"
        data = self.json(f"{self.base}/initSession", {**self.headers(), "Authorization": auth})
        self._session = _text(data.get("session_token")) if isinstance(data, dict) else ""
        if not self._session:
            raise SourceError("GLPI non ha aperto la sessione: controlla token e App-Token")

    def get(self, path: str, params: dict | None = None) -> tuple[Any, dict]:
        self.session()
        body, headers = self.http(f"{self.base}/{path}" + (f"?{urlencode(params)}" if params else ""), self.headers())
        return self.parse(body), headers

    def all(self, itemtype: str, params: dict | None = None) -> list[dict]:
        items: list[dict] = []
        start = 0
        while True:
            data, headers = self.get(itemtype, {**(params or {}), "range": f"{start}-{start + PAGE - 1}"})
            if not isinstance(data, list):
                raise SourceError(f"Risposta inattesa da GLPI ({itemtype})")
            items.extend(x for x in data if isinstance(x, dict))
            total = re.search(r"/(\d+)", headers.get("Content-Range") or headers.get("content-range") or "")
            start += PAGE
            if not data or not total or start >= int(total.group(1)):
                return items

    def optional(self, itemtype: str, what: str) -> list[dict]:
        try:
            return self.all(itemtype)
        except SourceError as exc:
            self.notes.append(f"{what} non letti da GLPI: {exc}")
            return []

    def version(self) -> str:
        try:
            data, _ = self.get("getGlpiConfig")
            return _text((data.get("cfg_glpi") or {}).get("version")) or "?"
        except SourceError:
            self.session()  # la configurazione può non essere leggibile: basta che la sessione si apra
            return "?"

    def close(self) -> None:
        if self._session:
            try:
                self.http(f"{self.base}/killSession", self.headers())
            except SourceError:
                pass

    def equipment(self) -> list[dict]:
        items = self.all("NetworkEquipment", {"expand_dropdowns": "true"})
        return [x for x in items if not x.get("is_deleted") and not x.get("is_template")]

    @staticmethod
    def place(x: dict) -> list[str]:
        return [p.strip() for p in _dropdown(x.get("locations_id")).split(">") if p.strip()]

    def probe(self) -> dict:
        version = self.version()
        equipment = self.equipment()
        per_site = Counter((self.place(x) or [""])[0] for x in equipment)
        groups = [{"id": name, "name": name or "(senza posizione)", "devices": n} for name, n in per_site.items()]
        return {"version": version, "counts": {"devices": len(equipment), "groups": len(groups)},
                "groups": sorted(groups, key=lambda g: g["name"].lower())}

    def fetch(self, group_ids: set | None, progress: Callable[[str], None], default_site: str) -> Snapshot:
        equipment = self.equipment()
        if group_ids:
            equipment = [x for x in equipment if (self.place(x) or [""])[0] in {str(g) for g in group_ids}]
            self.chosen_names = sorted({(self.place(x) or ["(senza posizione)"])[0] for x in equipment})
        progress(f"Letti da GLPI: {len(equipment)} apparati di rete")
        ports = [p for p in self.optional("NetworkPort", "Porte")
                 if p.get("itemtype") == "NetworkEquipment" and not p.get("is_deleted")]
        names = {str(n.get("id")): n for n in self.optional("NetworkName", "Nomi di rete")}
        addresses = [a for a in self.optional("IPAddress", "Indirizzi IP") if not a.get("is_deleted")]
        wiring = self.optional("NetworkPort_NetworkPort", "Collegamenti tra porte")
        progress(f"Letti da GLPI: {len(ports)} porte, {len(addresses)} indirizzi IP, {len(wiring)} collegamenti")
        for note in self.notes:
            progress(note)

        b = Builder(default_site)
        devices: dict[str, int] = {}
        for x in equipment:
            place = self.place(x)
            site = b.site(place[0] if place else None)
            devices[str(x.get("id"))] = b.device(
                x.get("name"), site, location=b.location(site, place[1:]), role=b.role(_dropdown(x.get("networkequipmenttypes_id"))),
                device_type=b.device_type(_dropdown(x.get("manufacturers_id")),
                                          _dropdown(x.get("networkequipmentmodels_id"))),
                serial=x.get("serial"), asset_tag=x.get("otherserial"), description=x.get("comment"))
        ports_by_id: dict[str, int] = {}
        for p in sorted(ports, key=lambda p: (p.get("logical_number") or 0, _text(p.get("name")))):
            device = devices.get(str(p.get("items_id")))
            if device is not None:
                ports_by_id[str(p.get("id"))] = b.interface(
                    device, p.get("name") or f"porta {p.get('logical_number')}", mac=p.get("mac"),
                    type=self.PORT_TYPES.get(_text(p.get("instantiation_type")).lower(), "other"),
                    description=p.get("comment"))
        for a in addresses:
            name = names.get(str(a.get("items_id"))) if a.get("itemtype") == "NetworkName" else None
            port = ports_by_id.get(str(name.get("items_id"))) if name and name.get("itemtype") == "NetworkPort" else None
            if port:
                b.ip(a.get("name"), port, name.get("name") if name else "")
        for device, ips in b.device_ips.items():  # il primo IP dell'apparato è quello di management
            b.management_ip(device, ips[0][0])
        for w in wiring:
            a, c = ports_by_id.get(str(w.get("networkports_id_1"))), ports_by_id.get(str(w.get("networkports_id_2")))
            if a and c:
                b.cable(a, c)
        return b.snap


# ---------------------------------------------------------------- Lansweeper
class Lansweeper(HttpSource):
    """API GraphQL di Lansweeper (cloud) con un token personale. Si scelgono i siti di Lansweeper (diventano sedi);
    si importano solo gli apparati di rete (switch, router, firewall, access point, stampanti, UPS, NAS…)."""

    key, label, group_label = "lansweeper", "Lansweeper", "siti"
    DEFAULT_URL = "https://api.lansweeper.com/api/v2/graphql"
    NETWORK_TYPES = {"switch", "router", "firewall", "wireless access point", "access point", "network device",
                     "printer", "ups", "nas", "san", "load balancer", "wireless controller", "modem", "gateway",
                     "pdu", "ip camera", "camera", "voip gateway"}
    FIELDS = ["key", "assetBasicInfo.name", "assetBasicInfo.type", "assetBasicInfo.ipAddress", "assetBasicInfo.mac",
              "assetBasicInfo.description", "assetCustom.manufacturer", "assetCustom.model",
              "assetCustom.serialNumber", "assetCustom.location", "assetCustom.barCode"]
    QUERY = """query assets($site: ID!, $pagination: AssetsPaginationInputValidated, $fields: [String!]!) {
  site(id: $site) { assetResources(assetPagination: $pagination, fields: $fields) {
    total pagination { limit current next page } items } } }"""

    def __init__(self, url: str, secrets: dict, username: str | None, verify_tls: bool):
        super().__init__(verify_tls)
        base = normalize_url(url or self.DEFAULT_URL, self.label)
        self.endpoint = base if base.endswith("graphql") else f"{base}/api/v2/graphql"
        self.token = secrets.get("token") or ""
        self.chosen_names: list[str] = []
        self._sites: list[dict] | None = None

    def query(self, text: str, variables: dict | None = None) -> dict:
        body = json.dumps({"query": text, "variables": variables or {}}).encode()
        data = self.json(self.endpoint, {"Authorization": f"Token {self.token}", "Content-Type": "application/json"}, body)
        if not isinstance(data, dict):
            raise SourceError("Risposta inattesa: l'indirizzo è quello dell'API di Lansweeper?")
        if data.get("errors"):
            message = _text((data["errors"][0] or {}).get("message"))
            if re.search(r"auth|token|permission|forbidden", message, re.IGNORECASE):
                raise SourceError(f"Lansweeper rifiuta le credenziali: {message}")
            raise SourceError(f"Lansweeper ha risposto con un errore: {message}")
        return data.get("data") or {}

    def sites(self) -> list[dict]:
        if self._sites is None:
            data = self.query("query { authorizedSites { sites { id name } } }")
            self._sites = [s for s in (data.get("authorizedSites") or {}).get("sites") or [] if isinstance(s, dict)]
        return self._sites

    def version(self) -> str:
        self.sites()
        return "cloud"

    def assets(self, site: str, limit: int = PAGE) -> tuple[list[dict], int]:
        items: list[dict] = []
        pagination: dict = {"limit": limit, "page": "FIRST"}
        while True:
            data = self.query(self.QUERY, {"site": site, "pagination": pagination, "fields": self.FIELDS})
            resources = ((data.get("site") or {}).get("assetResources")) or {}
            items.extend(x for x in resources.get("items") or [] if isinstance(x, dict))
            following = (resources.get("pagination") or {}).get("next")
            if limit < PAGE or not following or not resources.get("items"):
                return items, int(resources.get("total") or len(items))
            pagination = {"limit": limit, "page": "NEXT", "cursor": following}

    def probe(self) -> dict:
        groups = [{"id": s["id"], "name": _text(s.get("name")) or s["id"], "devices": self.assets(s["id"], 1)[1]}
                  for s in self.sites()]
        return {"version": "cloud", "counts": {"devices": sum(g["devices"] for g in groups), "groups": len(groups)},
                "groups": sorted(groups, key=lambda g: g["name"].lower())}

    def fetch(self, group_ids: set | None, progress: Callable[[str], None], default_site: str) -> Snapshot:
        sites = [s for s in self.sites() if not group_ids or s["id"] in {str(g) for g in group_ids}]
        self.chosen_names = sorted(_text(s.get("name")) or s["id"] for s in sites)
        b = Builder(default_site)
        for s in sites:
            assets, _ = self.assets(s["id"])
            network = [a for a in assets if _text((a.get("assetBasicInfo") or {}).get("type")).lower() in self.NETWORK_TYPES]
            progress(f"Letti da Lansweeper ({s.get('name')}): {len(assets)} asset, {len(network)} apparati di rete "
                     f"(gli altri, come computer e telefoni, non si importano)")
            site = b.site(s.get("name"))
            for a in network:
                basic, custom = a.get("assetBasicInfo") or {}, a.get("assetCustom") or {}
                device = b.device(
                    basic.get("name"), site, location=b.location(site, [custom.get("location")]),
                    role=b.role(basic.get("type")), device_type=b.device_type(custom.get("manufacturer"), custom.get("model")),
                    serial=custom.get("serialNumber"), asset_tag=custom.get("barCode"), description=basic.get("description"))
                b.management_ip(device, basic.get("ipAddress"), basic.get("mac"))
        return b.snap


SOURCES = {cls.key: cls for cls in (Zabbix, LibreNMS, Observium, PRTG, GLPI, Lansweeper)}


def build(source: str, url: str, secrets: dict, username: str | None, verify_tls: bool):
    cls = SOURCES.get(source)
    if cls is None:
        raise SourceError(f"Sorgente sconosciuta: {source}")
    return cls(url, secrets, username, verify_tls)
