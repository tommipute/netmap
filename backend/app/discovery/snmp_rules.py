"""Regole SNMP: correzioni alla lettura di un tipo di apparato, scritte dall'amministratore senza toccare il codice.

Una regola vale per gli apparati con un certo inizio del sysObjectID e/o una descrizione SNMP che corrisponde a
un'espressione regolare, e cambia solo cose di un elenco fisso: modello e seriale (da un OID del produttore o dalla
descrizione, o un'espressione sul valore dell'OID), nome delle porte (ifName, ifDescr o ifAlias), porte da ignorare, produttore, tipo di apparato, come
leggere le porte della tabella MAC e la porta locale dei vicini LLDP.
Si applicano alla fine della lettura (`snmp._read_host`); il collector non tocca il database, quindi le regole
arrivano già compilate (`compile_rule`).

Più regole sullo stesso apparato: vince la più precisa (sysObjectID più lungo, poi quella che guarda anche la
descrizione, poi la più vecchia), una cosa per volta: una regola che imposta solo il seriale non toglie il modello
di un'altra. Le regole incluse in NetMap (`builtin_rules.json`) vengono sempre dopo quelle dell'amministratore.
"""
import re
from dataclasses import dataclass
from typing import Any

PORT_NAME_SOURCES = ("name", "descr", "alias")  # ifName (predefinito), ifDescr, ifAlias
# Campi di una regola nell'API, nel file di export/import e in builtin_rules.json (senza id, date, builtin)
FIELDS = ("name", "enabled", "description", "match_object_id", "match_descr", "model_oid", "model_regex", "serial_oid",
          "port_name", "ignore_ports", "ignore_if_types", "manufacturer", "kind", "fdb_port", "lldp_port_oid")
# Porta di una riga della tabella MAC che non è una porta bridge: la n-esima porta bridge (TP-Link JetStream) o l'ifIndex
FDB_PORT_MODES = ("position", "ifindex")
_OID = re.compile(r"^\d+(\.\d+)+$")


def clean_oid(value: str | None) -> str | None:
    """"  .1.3.6.1.4.1.9. " -> "1.3.6.1.4.1.9"; None se vuoto."""
    if value is None:
        return None
    value = value.strip().strip(".")
    return value or None


def check_oid(value: str) -> str:
    if not _OID.match(value):
        raise ValueError(f"OID non valido: {value} (scrivilo con i numeri, es. 1.3.6.1.4.1.11863.6.1.1.7)")
    return value


def check_regex(value: str) -> str:
    try:
        re.compile(value)
    except re.error as exc:
        raise ValueError(f"Espressione regolare non valida: {exc}") from exc
    return value


@dataclass
class Rule:
    name: str
    sys_object_id: str | None = None
    sys_descr: re.Pattern | None = None
    model_oid: str | None = None
    model_regex: re.Pattern | None = None
    serial_oid: str | None = None
    port_name: str | None = None
    ignore_ports: re.Pattern | None = None
    ignore_if_types: tuple[int, ...] = ()
    manufacturer: str | None = None
    kind: str | None = None
    fdb_port: str | None = None
    lldp_port_oid: str | None = None  # colonna indicizzata da lldpRemIndex con l'ifIndex della porta locale
    builtin: bool = False
    order: int = 0  # a parità di precisione vince la più vecchia (id più basso)

    def matches(self, sys_object_id: str | None, sys_descr: str | None) -> bool:
        if self.sys_object_id is None and self.sys_descr is None:
            return False
        if self.sys_object_id is not None:
            oid = (sys_object_id or "").strip(".")
            if oid != self.sys_object_id and not oid.startswith(self.sys_object_id + "."):
                return False
        return self.sys_descr is None or bool(self.sys_descr.search(sys_descr or ""))

    def precision(self) -> tuple:
        return (self.builtin, -len(self.sys_object_id.split(".")) if self.sys_object_id else 0, self.sys_descr is None,
                self.order)


def compile_rule(row: Any) -> Rule:
    """Regola dal database (o dalla prova nel modulo, con gli stessi campi)."""
    def pattern(text: str | None) -> re.Pattern | None:
        return re.compile(text, re.IGNORECASE) if text else None

    return Rule(
        name=row.name,
        sys_object_id=clean_oid(row.match_object_id),
        sys_descr=pattern(row.match_descr),
        model_oid=clean_oid(row.model_oid),
        model_regex=pattern(row.model_regex),
        serial_oid=clean_oid(row.serial_oid),
        port_name=row.port_name,
        ignore_ports=pattern(row.ignore_ports),
        ignore_if_types=tuple(row.ignore_if_types or ()),
        manufacturer=(row.manufacturer or "").strip() or None,
        kind=row.kind,
        fdb_port=getattr(row, "fdb_port", None),
        lldp_port_oid=clean_oid(getattr(row, "lldp_port_oid", None)),
        builtin=bool(getattr(row, "builtin", False)),
        order=row.id or 0,
    )


def matching(rules: list[Rule], sys_object_id: str | None, sys_descr: str | None) -> list[Rule]:
    """Regole che valgono per l'apparato, dalla più precisa."""
    return sorted((r for r in rules if r.matches(sys_object_id, sys_descr)), key=Rule.precision)


def oids(rules: list[Rule]) -> list[str]:
    """OID con un valore solo da leggere in più per queste regole."""
    return list(dict.fromkeys(o for r in rules for o in (r.model_oid, r.serial_oid) if o))


def tables(rules: list[Rule]) -> list[str]:
    """Colonne da leggere per queste regole (porta locale dei vicini LLDP)."""
    return list(dict.fromkeys(r.lldp_port_oid for r in rules if r.lldp_port_oid))


def _text(value: Any) -> str | None:
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="replace")
    if value is None:
        return None
    text = " ".join(str(value).replace("\x00", "").split())
    return text or None


def _from_descr(pattern: re.Pattern, sys_descr: str | None) -> str | None:
    found = pattern.search(sys_descr or "")
    if not found:
        return None
    return _text(next((g for g in found.groups() if g), None) if found.groups() else found.group(0))


def apply(data: Any, rules: list[Rule], values: dict[str, Any]) -> None:
    """Applica a `data` (snmp.HostData) le regole già filtrate e ordinate da `matching`; `values` = OID letti.
    Le porte con un indirizzo IP non si ignorano mai: spesso è quella di management (Vlan1, vlanif)."""
    for rule in rules:
        # l'espressione si applica al valore dell'OID se c'è (per togliere la versione), altrimenti alla descrizione
        model = _text(values.get(rule.model_oid)) if rule.model_oid else None
        if rule.model_regex:
            model = _from_descr(rule.model_regex, model or data.sys_descr)
        if model:
            data.model, data.model_source = model[:100], "rule"
            break
    for rule in rules:
        if rule.serial_oid and (serial := _text(values.get(rule.serial_oid))):
            data.serial = serial[:100]
            break

    _fdb_ports(data, next((r for r in rules if r.fdb_port), None))
    _lldp_ports(data, next((r for r in rules if r.lldp_port_oid), None), values)

    if rule := next((r for r in rules if r.port_name), None):
        for iface in data.interfaces:
            name = _text({"name": None, "descr": iface.descr, "alias": iface.alias}[rule.port_name])
            if name and rule.port_name != "name":
                iface.name = name[:100]

    by_name = next((r for r in rules if r.ignore_ports), None)
    by_type = next((r for r in rules if r.ignore_if_types), None)
    if by_name or by_type:
        with_ip = {ip.if_index for ip in data.ips}  # la porta con l'IP di management non si perde mai
        gone = {
            i.if_index for i in data.interfaces
            if i.if_index not in with_ip and (
                (by_name and by_name.ignore_ports.search(i.name))
                or (by_type and i.if_type in by_type.ignore_if_types))
        }
        if gone:
            data.interfaces = [i for i in data.interfaces if i.if_index not in gone]
            data.fdb = [e for e in data.fdb if e.if_index not in gone]
            data.arp = [a if a.if_index not in gone else type(a)(ip=a.ip, mac=a.mac) for a in data.arp]
            data.neighbors = [n for n in data.neighbors if n.local_if_index not in gone]
            data.port_vlans = {k: v for k, v in data.port_vlans.items() if k not in gone}
            data.port_tagged = {k: v for k, v in data.port_tagged.items() if k not in gone}
            data.notes["ports_ignored"] = len(gone)

    if rule := next((r for r in rules if r.manufacturer), None):
        data.manufacturer = rule.manufacturer[:100]
    if rule := next((r for r in rules if r.kind), None):
        data.kind = rule.kind
    data.rules = [r.name for r in rules]  # per la scheda "Cosa ho letto"
    data.rule_ids = [r.order for r in rules]


def _fdb_ports(data: Any, rule: Rule | None) -> None:
    """Righe della tabella MAC scartate perché la porta non era una porta bridge, lette come dice la regola."""
    if rule is None or not data.fdb_unmapped:
        return
    from app.discovery.snmp import FdbEntry  # snmp importa questo modulo

    if_indexes = {i.if_index for i in data.interfaces}
    by_position = dict(enumerate(sorted(data.bridge_ports), start=1))
    seen = {(e.mac, e.if_index, e.vlan) for e in data.fdb}
    mapped = 0
    for mac, port, vlan in data.fdb_unmapped:
        if rule.fdb_port == "position":
            if_index = data.bridge_ports.get(by_position.get(port))
        else:
            if_index = port if port in if_indexes else None
        if if_index is None:
            continue
        mapped += 1
        vlan = vlan if vlan is not None else data.port_vlans.get(if_index)
        if (mac, if_index, vlan) not in seen:
            seen.add((mac, if_index, vlan))
            data.fdb.append(FdbEntry(mac=mac, if_index=if_index, vlan=vlan))
    if mapped:
        data.fdb.sort(key=lambda e: (e.mac, e.if_index, e.vlan or 0))
        data.fdb_source = data.fdb_source or data.fdb_table
        data.notes["fdb_port_rule"] = mapped
        left = data.notes.get("fdb_unmapped", 0) - mapped
        if left > 0:
            data.notes["fdb_unmapped"] = left
        else:
            data.notes.pop("fdb_unmapped", None)


def _lldp_ports(data: Any, rule: Rule | None, values: dict[str, Any]) -> None:
    """Porta locale dei vicini LLDP che non ce l'hanno (RouterOS 6), da una colonna indicizzata da lldpRemIndex."""
    table = values.get(rule.lldp_port_oid) if rule else None
    if not isinstance(table, dict):
        return
    if_indexes = {i.if_index for i in data.interfaces}
    found = 0
    for neighbor in data.neighbors:
        if neighbor.protocol == "lldp" and neighbor.local_if_index is None and neighbor.rem_index is not None:
            port = table.get(neighbor.rem_index)
            if isinstance(port, int) and port in if_indexes:
                neighbor.local_if_index = port
                found += 1
    if found:
        data.notes["lldp_port_rule"] = found
