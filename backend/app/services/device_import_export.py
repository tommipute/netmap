"""Servizio di import ed export per i device e le relative informazioni."""
import csv
import io
import json
from typing import Any

from fastapi import HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.exc import DataError, IntegrityError
from sqlalchemy.orm import Session

from app.models import (
    Device,
    DeviceRole,
    DeviceType,
    Interface,
    IPAddress,
    Location,
    Manufacturer,
    Rack,
    Site,
)
from app.models.enums import DeviceStatus
from app.services.locations import SEPARATOR
from app.services.rules import device_hook, set_management_ip

# Mappatura sinonimi/alias per le intestazioni CSV (italiano e inglese)
HEADER_ALIASES: dict[str, list[str]] = {
    "name": ["name", "nome", "device", "dispositivo", "hostname", "device_name"],
    "status": ["status", "stato"],
    "site": ["site", "sede", "site_name", "nome_sede"],
    "location": ["location", "posizione", "luogo", "stanza", "piano", "ubicazione"],
    "rack": ["rack", "armadio"],
    "rack_position": ["rack_position", "u", "posizione_rack", "rack_pos", "unit", "unita"],
    "manufacturer": ["manufacturer", "produttore", "marca", "vendor", "costruttore"],
    "model": ["model", "modello", "device_type", "tipo_device", "part_number"],
    "role": ["role", "ruolo", "device_role"],
    "primary_ip": ["primary_ip", "ip", "ip_address", "ip_primario", "indirizzo_ip", "mgmt_ip", "ip_management"],
    "serial": ["serial", "seriale", "sn", "serial_number", "numero_serie"],
    "asset_tag": ["asset_tag", "asset", "cespite", "tag"],
    "description": ["description", "descrizione", "note", "notes", "dettagli"],
}

VALID_STATUSES = {s.value for s in DeviceStatus}


def _normalize_header(h: str) -> str:
    cleaned = h.strip().lower().replace(" ", "_").replace("-", "_")
    for standard_name, aliases in HEADER_ALIASES.items():
        if cleaned in aliases:
            return standard_name
    return cleaned


def get_devices_data(
    db: Session,
    site_id: int | None = None,
    location_id: int | None = None,
    rack_id: int | None = None,
    role_id: int | None = None,
    device_type_id: int | None = None,
    status: str | None = None,
    q: str | None = None,
    only_ids=None,
) -> list[dict[str, Any]]:
    """Estrae l'elenco dei device con tutte le relative informazioni risolte (only_ids: select di id da tenere)."""
    stmt = select(Device)
    if only_ids is not None:
        stmt = stmt.where(Device.id.in_(only_ids))
    if site_id:
        stmt = stmt.where(Device.site_id == site_id)
    if location_id:
        stmt = stmt.where(Device.location_id == location_id)
    if rack_id:
        stmt = stmt.where(Device.rack_id == rack_id)
    if role_id:
        stmt = stmt.where(Device.role_id == role_id)
    if device_type_id:
        stmt = stmt.where(Device.device_type_id == device_type_id)
    if status:
        stmt = stmt.where(Device.status == status)
    if q:
        term = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                Device.name.ilike(term),
                Device.serial.ilike(term),
                Device.asset_tag.ilike(term),
                Device.sys_name.ilike(term),
                Device.description.ilike(term),
            )
        )
    stmt = stmt.order_by(Device.name)
    devices = list(db.scalars(stmt))

    # Carica cache delle entità collegate per performance istantanee
    sites = {s.id: s.name for s in db.scalars(select(Site))}
    locations = {l.id: l.path or l.name for l in db.scalars(select(Location))}
    racks = {r.id: r.name for r in db.scalars(select(Rack))}
    device_types = {dt.id: dt for dt in db.scalars(select(DeviceType))}
    manufacturers = {m.id: m.name for m in db.scalars(select(Manufacturer))}
    roles = {r.id: r.name for r in db.scalars(select(DeviceRole))}

    # Primary IPs con nome porta e MAC
    stmt_ip = (
        select(Interface.device_id, IPAddress.address, IPAddress.host, Interface.name, Interface.mac_address)
        .join(IPAddress, IPAddress.interface_id == Interface.id)
        .where(IPAddress.is_primary.is_(True))
    )
    primary_ips: dict[int, dict[str, Any]] = {}
    for dev_id, addr, host, iface_name, mac in db.execute(stmt_ip):
        primary_ips[dev_id] = {
            "address": addr,
            "host": host,
            "interface": iface_name,
            "mac": mac,
        }

    # Conteggio porte
    stmt_ports = select(Interface.device_id, func.count(Interface.id)).group_by(Interface.device_id)
    port_counts = dict(db.execute(stmt_ports).all())

    items = []
    for d in devices:
        dt = device_types.get(d.device_type_id) if d.device_type_id else None
        mfg_name = manufacturers.get(dt.manufacturer_id) if dt and dt.manufacturer_id else None
        model_name = dt.model if dt else None
        pip = primary_ips.get(d.id, {})

        items.append({
            "id": d.id,
            "name": d.name,
            "status": d.status,
            "site": sites.get(d.site_id, ""),
            "site_id": d.site_id,
            "location": locations.get(d.location_id, "") if d.location_id else "",
            "location_id": d.location_id,
            "rack": racks.get(d.rack_id, "") if d.rack_id else "",
            "rack_id": d.rack_id,
            "rack_position": d.rack_position if d.rack_position is not None else "",
            "manufacturer": mfg_name or "",
            "model": model_name or "",
            "device_type_id": d.device_type_id,
            "role": roles.get(d.role_id, "") if d.role_id else "",
            "role_id": d.role_id,
            "primary_ip": pip.get("address", ""),
            "primary_ip_host": pip.get("host", ""),
            "primary_interface": pip.get("interface", ""),
            "primary_mac": pip.get("mac", "") or "",
            "serial": d.serial or "",
            "asset_tag": d.asset_tag or "",
            "sys_name": d.sys_name or "",
            "ports_count": port_counts.get(d.id, 0),
            "description": d.description or "",
        })
    return items


def export_devices(
    db: Session,
    format: str = "csv",
    delimiter: str = ";",
    site_id: int | None = None,
    location_id: int | None = None,
    rack_id: int | None = None,
    role_id: int | None = None,
    device_type_id: int | None = None,
    status: str | None = None,
    q: str | None = None,
    only_ids=None,
) -> tuple[str, str, str]:
    """Genera l'export in CSV o JSON.

    Ritorna (content, media_type, filename).
    """
    items = get_devices_data(
        db,
        site_id=site_id,
        location_id=location_id,
        rack_id=rack_id,
        role_id=role_id,
        device_type_id=device_type_id,
        status=status,
        q=q,
        only_ids=only_ids,
    )

    if format == "json":
        content = json.dumps(items, ensure_ascii=False, indent=2)
        return content, "application/json; charset=utf-8", "devices_export.json"

    # Export CSV con BOM UTF-8 (compatibilità perfetta con Microsoft Excel su Windows)
    output = io.StringIO()
    output.write("\ufeff")

    fieldnames = [
        "name",
        "status",
        "site",
        "location",
        "rack",
        "rack_position",
        "manufacturer",
        "model",
        "role",
        "primary_ip",
        "primary_mac",
        "serial",
        "asset_tag",
        "ports_count",
        "description",
    ]
    delim = delimiter if delimiter in (",", ";", "\t") else ";"
    writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore", delimiter=delim)
    writer.writeheader()
    for item in items:
        writer.writerow(item)

    return output.getvalue(), "text/csv; charset=utf-8", "devices_export.csv"


def generate_device_csv_template(delimiter: str = ";") -> str:
    """Genera un modello CSV di esempio compilabile dall'utente."""
    output = io.StringIO()
    output.write("\ufeff")
    delim = delimiter if delimiter in (",", ";", "\t") else ";"
    fieldnames = [
        "name",
        "status",
        "site",
        "location",
        "rack",
        "rack_position",
        "manufacturer",
        "model",
        "role",
        "primary_ip",
        "serial",
        "asset_tag",
        "description",
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames, delimiter=delim)
    writer.writeheader()
    writer.writerow({
        "name": "sw-core-01",
        "status": "active",
        "site": "Sede principale",
        "location": "Sala Server",
        "rack": "RACK-01",
        "rack_position": "42",
        "manufacturer": "Cisco",
        "model": "Catalyst 9300-48P",
        "role": "Core",
        "primary_ip": "10.10.99.1/24",
        "serial": "FOC2401ABCD",
        "asset_tag": "AST-0001",
        "description": "Switch core di centro stella",
    })
    writer.writerow({
        "name": "sw-p1-01",
        "status": "active",
        "site": "Sede principale",
        "location": "Piano 1",
        "rack": "RACK-P1",
        "rack_position": "20",
        "manufacturer": "HPE Aruba",
        "model": "2930F-48G",
        "role": "Switch",
        "primary_ip": "10.10.99.11/24",
        "serial": "SG81452399",
        "asset_tag": "AST-0002",
        "description": "Switch accesso piano 1",
    })
    writer.writerow({
        "name": "fw-edge-01",
        "status": "active",
        "site": "Filiale Roma",
        "location": "CED",
        "rack": "RACK-01",
        "rack_position": "40",
        "manufacturer": "Fortinet",
        "model": "FortiGate 60F",
        "role": "Firewall",
        "primary_ip": "192.168.100.1/24",
        "serial": "FGT60FTK21001",
        "asset_tag": "AST-0003",
        "description": "Firewall perimetrale filiale",
    })
    return output.getvalue()


# ---------------------------------------------------------------- import

# Stati scritti in italiano (come nell'interfaccia) -> valore salvato
STATUS_ALIASES = {
    "attivo": DeviceStatus.ACTIVE.value,
    "pianificato": DeviceStatus.PLANNED.value,
    "spento": DeviceStatus.OFFLINE.value,
    "dismesso": DeviceStatus.DECOMMISSIONED.value,
}
class RowError(Exception):
    """Errore di una singola riga: la riga viene saltata, le altre proseguono."""


def _result(dry_run: bool, error: str | None = None) -> dict[str, Any]:
    return {
        "total_rows": 0,
        "created_count": 0,
        "updated_count": 0,
        "skipped_count": 0,
        "errors": [{"row": 0, "error": error}] if error else [],
        "created_devices": [],
        "updated_devices": [],
        "skipped_devices": [],
        "dry_run": dry_run,
    }


def _text(row: dict[str, str], key: str, label: str, max_length: int = 100) -> str:
    value = row.get(key, "").strip()
    if len(value) > max_length:
        raise RowError(f"{label} troppo lungo: massimo {max_length} caratteri")
    return value


def _by_id_or_name(db: Session, model, value: str, name_column, *conditions):
    """Cerca per id numerico o per nome (senza distinguere maiuscole)."""
    if value.isdigit():
        obj = db.get(model, int(value))
        if obj is not None:
            return obj
    return db.scalars(select(model).where(func.lower(name_column) == value.lower(), *conditions)).first()


def _get_or_create_manufacturer(db: Session, name: str) -> Manufacturer:
    manufacturer = db.scalars(select(Manufacturer).where(func.lower(Manufacturer.name) == name.lower())).first()
    if manufacturer is None:
        manufacturer = Manufacturer(name=name)
        db.add(manufacturer)
        db.flush()
    return manufacturer


def _resolve_site(db: Session, value: str) -> Site:
    if not value:
        site = db.scalars(select(Site).order_by(Site.id)).first()
        if site:
            return site
        value = "Sede principale"
    site = _by_id_or_name(db, Site, value, Site.name)
    if site is None:
        site = Site(name=value)
        db.add(site)
        db.flush()
    return site


def _resolve_location(db: Session, site: Site, value: str) -> Location | None:
    if not value:
        return None
    # Percorso completo ("Palazzina A › P1", come nell'export; va bene anche ">") oppure solo il nome
    value = SEPARATOR.join(part.strip() for part in value.replace(">", "›").split("›"))
    location = db.scalars(select(Location).where(
        Location.site_id == site.id, func.lower(Location.path) == value.lower(),
    )).first()
    if location is None and SEPARATOR not in value:
        location = _by_id_or_name(db, Location, value, Location.name, Location.site_id == site.id)
    if location is None:
        # Mancano: creo i livelli che non ci sono, dal più alto
        parent = None
        for name in [part for part in value.split(SEPARATOR) if part]:
            found = db.scalar(select(Location).where(
                Location.site_id == site.id, func.lower(Location.name) == name.lower(),
                Location.parent_id == parent.id if parent else Location.parent_id.is_(None),
            ))
            if found is None:
                found = Location(site_id=site.id, parent_id=parent.id if parent else None, name=name)
                db.add(found)
                db.flush()
            parent = found
        location = parent
    return location


def _resolve_rack(db: Session, site: Site, location: Location | None, value: str) -> Rack | None:
    if not value:
        return None
    rack = _by_id_or_name(db, Rack, value, Rack.name, Rack.site_id == site.id)
    if rack is None:
        rack = Rack(site_id=site.id, location_id=location.id if location else None, name=value)
        db.add(rack)
        db.flush()
    return rack


def _resolve_device_type(db: Session, manufacturer_name: str, model: str) -> DeviceType | None:
    if not model:
        return None
    if manufacturer_name:
        manufacturer = _get_or_create_manufacturer(db, manufacturer_name)
        dev_type = _by_id_or_name(db, DeviceType, model, DeviceType.model, DeviceType.manufacturer_id == manufacturer.id)
    else:
        manufacturer = None
        dev_type = _by_id_or_name(db, DeviceType, model, DeviceType.model)
    if dev_type is None:
        manufacturer = manufacturer or _get_or_create_manufacturer(db, "Generico")
        dev_type = DeviceType(manufacturer_id=manufacturer.id, model=model, u_height=1)
        db.add(dev_type)
        db.flush()
    return dev_type


def _resolve_role(db: Session, value: str) -> DeviceRole | None:
    if not value:
        return None
    role = _by_id_or_name(db, DeviceRole, value, DeviceRole.name)
    if role is not None:
        return role
    r_lower = value.lower()
    lvl, col = 2, "#888780"
    if "firewall" in r_lower or "gw" in r_lower or "router" in r_lower:
        lvl, col = 0, "#E24B4B"
    elif "core" in r_lower:
        lvl, col = 0, "#2B7FFF"
    elif "distrib" in r_lower:
        lvl, col = 1, "#4FA8F6"
    elif "access" in r_lower or "switch" in r_lower:
        lvl, col = 2, "#10B981"
    elif "ap" in r_lower.split() or "wifi" in r_lower or "wi-fi" in r_lower:
        lvl, col = 3, "#F59E0B"
    role = DeviceRole(name=value, level=lvl, color=col)
    db.add(role)
    db.flush()
    return role


def _parse_status(value: str) -> str | None:
    if not value:
        return None
    value = value.lower()
    status = STATUS_ALIASES.get(value, value)
    if status not in VALID_STATUSES:
        raise RowError(
            f"Stato non valido: '{value}'. Usa attivo, pianificato, offline o dismesso "
            "(oppure active, planned, offline, decommissioned)"
        )
    return status


def _parse_rack_position(value: str) -> int | None:
    if not value:
        return None
    if not value.isdigit() or not 1 <= int(value) <= 60:
        raise RowError(f"Unità nel rack non valida: '{value}' (serve un numero da 1 a 60)")
    return int(value)


def _import_row(db: Session, row: dict[str, str], update_existing: bool) -> str:
    """Crea o aggiorna il device di una riga. Ritorna 'created', 'updated' o 'skipped'."""
    name = _text(row, "name", "Nome")
    if not name:
        raise RowError("Nome del device vuoto")
    status = _parse_status(row.get("status", "").strip())
    rack_position = _parse_rack_position(row.get("rack_position", "").strip())
    serial = _text(row, "serial", "Numero di serie")
    asset_tag = _text(row, "asset_tag", "Asset tag")
    description = row.get("description", "").strip()

    site = _resolve_site(db, _text(row, "site", "Sede"))
    location = _resolve_location(db, site, _text(row, "location", "Posizione"))
    rack = _resolve_rack(db, site, location, _text(row, "rack", "Rack"))
    dev_type = _resolve_device_type(db, _text(row, "manufacturer", "Produttore"), _text(row, "model", "Modello"))
    role = _resolve_role(db, _text(row, "role", "Ruolo"))

    device = db.scalars(
        select(Device).where(Device.site_id == site.id, func.lower(Device.name) == name.lower())
    ).first()
    if device is not None and not update_existing:
        return "skipped"
    outcome = "updated" if device is not None else "created"
    if device is None:
        device = Device(name=name, site_id=site.id, status=status or DeviceStatus.ACTIVE.value)
        db.add(device)

    # Si aggiornano solo le colonne presenti e compilate: una cella vuota lascia il valore com'è
    if status:
        device.status = status
    if location:
        device.location_id = location.id
    if rack:
        device.rack_id = rack.id
    if rack_position is not None:
        device.rack_position = rack_position
    if dev_type:
        device.device_type_id = dev_type.id
    if role:
        device.role_id = role.id
    if serial:
        device.serial = serial
    if description:
        device.description = description
    if asset_tag:
        owner = db.scalar(select(Device.name).where(Device.asset_tag == asset_tag, Device.id != device.id))
        if owner:
            raise RowError(f"Asset tag {asset_tag} già usato da {owner}")
        device.asset_tag = asset_tag

    device_hook(db, device, {}, outcome == "created")  # posizione e rack della stessa sede
    db.flush()

    ip_value = row.get("primary_ip", "").strip()
    if ip_value:
        set_management_ip(db, device, ip_value)
    return outcome


def import_devices_from_csv(
    db: Session,
    csv_text: str,
    update_existing: bool = True,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Importa device da una stringa CSV.

    Risolve (e se servono crea) sedi, posizioni, rack, produttori, modelli e ruoli e assegna l'IP primario.
    Ogni riga è in un SAVEPOINT: una riga sbagliata finisce tra gli errori senza bloccare le altre.
    Con dry_run alla fine si annulla tutto, ma gli errori segnalati sono gli stessi dell'import vero.
    """
    lines = csv_text.lstrip("﻿").splitlines()
    header_index = next((i for i, line in enumerate(lines) if line.strip()), None)
    if header_index is None:
        return _result(dry_run, "Il testo o file CSV fornito è vuoto.")

    first_line = lines[header_index]
    if "\t" in first_line:
        delim = "\t"
    elif first_line.count(";") >= first_line.count(","):
        delim = ";"
    else:
        delim = ","

    reader = csv.reader(io.StringIO("\n".join(lines)), delimiter=delim)
    for _ in range(header_index):
        next(reader)
    headers = [_normalize_header(h) for h in next(reader)]
    if "name" not in headers:
        return _result(dry_run, "Colonna obbligatoria 'name' (o 'nome') mancante nelle intestazioni.")

    result = _result(dry_run)
    for values in reader:
        if not any(v.strip() for v in values):
            continue
        result["total_rows"] += 1
        row = {h: v.strip() for h, v in zip(headers, values) if h}
        row_number = reader.line_num  # riga del file, intestazione compresa
        device_name = row.get("name") or None

        savepoint = db.begin_nested()
        try:
            outcome = _import_row(db, row, update_existing)
            savepoint.commit()
        except (RowError, HTTPException, IntegrityError, DataError) as exc:
            savepoint.rollback()
            if isinstance(exc, HTTPException):
                message = exc.detail
            elif isinstance(exc, (IntegrityError, DataError)):
                message = "Valore duplicato o non valido per il database"
            else:
                message = str(exc)
            result["errors"].append({"row": row_number, "device": device_name, "error": message})
            continue
        result[f"{outcome}_count"] += 1
        result[f"{outcome}_devices"].append(device_name)

    if dry_run:
        db.rollback()
    else:
        db.commit()
    return result
