"""Servizio di import ed export per i device e le relative informazioni."""
import csv
import io
import ipaddress
import json
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.net import normalize_ip_interface
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
from app.models.enums import DeviceStatus, InterfaceType
from app.services.rules import ip_hook

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
) -> list[dict[str, Any]]:
    """Estrae l'elenco dei device con tutte le relative informazioni risolte."""
    stmt = select(Device)
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
    locations = {l.id: l.name for l in db.scalars(select(Location))}
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


def import_devices_from_csv(
    db: Session,
    csv_text: str,
    update_existing: bool = True,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Importa device da una stringa CSV.

    Risolve automaticamente sedi, posizioni, rack, produttori, modelli, ruoli e assegna l'IP primario.
    Supporta dry-run e aggiornamento di device esistenti.
    """
    lines = [l for l in csv_text.splitlines() if l.strip()]
    if not lines:
        return {
            "total_rows": 0,
            "created_count": 0,
            "updated_count": 0,
            "skipped_count": 0,
            "errors": [{"row": 0, "error": "Il testo o file CSV fornito è vuoto."}],
            "created_devices": [],
            "updated_devices": [],
            "skipped_devices": [],
        }

    first_line = lines[0]
    if first_line.startswith("\ufeff"):
        first_line = first_line[1:]
        lines[0] = first_line

    # Rilevamento automatico del separatore
    delim = ","
    if ";" in first_line and first_line.count(";") >= first_line.count(","):
        delim = ";"
    elif "\t" in first_line:
        delim = "\t"

    reader = csv.reader(io.StringIO("\n".join(lines)), delimiter=delim)
    raw_headers = next(reader, None)
    if not raw_headers:
        return {
            "total_rows": 0,
            "created_count": 0,
            "updated_count": 0,
            "skipped_count": 0,
            "errors": [{"row": 0, "error": "Intestazioni del CSV non trovate."}],
            "created_devices": [],
            "updated_devices": [],
            "skipped_devices": [],
        }

    normalized_headers = [_normalize_header(h) for h in raw_headers]
    if "name" not in normalized_headers:
        return {
            "total_rows": 0,
            "created_count": 0,
            "updated_count": 0,
            "skipped_count": 0,
            "errors": [
                {
                    "row": 1,
                    "error": "Colonna obbligatoria 'name' (o 'nome') mancante nelle intestazioni.",
                }
            ],
            "created_devices": [],
            "updated_devices": [],
            "skipped_devices": [],
        }

    created_devices: list[str] = []
    updated_devices: list[str] = []
    skipped_devices: list[str] = []
    errors: list[dict[str, Any]] = []

    row_index = 1  # 1-indexed (la riga 1 erano le intestazioni)
    for row_values in reader:
        row_index += 1
        if not any(v.strip() for v in row_values):
            continue  # riga vuota

        row_dict = {}
        for h, val in zip(normalized_headers, row_values):
            if h:
                row_dict[h] = val.strip()

        dev_name = row_dict.get("name", "").strip()
        if not dev_name:
            errors.append({"row": row_index, "error": "Nome del device vuoto."})
            continue

        # 1. Sede (Site)
        site_val = row_dict.get("site", "").strip()
        site: Site | None = None
        if site_val:
            if site_val.isdigit():
                site = db.get(Site, int(site_val))
            if not site:
                site = db.scalars(select(Site).where(func.lower(Site.name) == site_val.lower())).first()
            if not site:
                # Creazione automatica della sede se non esiste
                site = Site(name=site_val)
                db.add(site)
                db.flush()
        else:
            # Se non indicata, prova a usare la prima sede esistente, o segnala errore
            first_site = db.scalars(select(Site).order_by(Site.id)).first()
            if first_site:
                site = first_site
            else:
                site = Site(name="Sede Principale")
                db.add(site)
                db.flush()

        # 2. Posizione (Location)
        loc_val = row_dict.get("location", "").strip()
        location: Location | None = None
        if loc_val:
            if loc_val.isdigit():
                location = db.get(Location, int(loc_val))
            if not location:
                location = db.scalars(
                    select(Location).where(
                        Location.site_id == site.id,
                        func.lower(Location.name) == loc_val.lower(),
                    )
                ).first()
            if not location:
                location = Location(site_id=site.id, name=loc_val)
                db.add(location)
                db.flush()

        # 3. Rack
        rack_val = row_dict.get("rack", "").strip()
        rack: Rack | None = None
        if rack_val:
            if rack_val.isdigit():
                rack = db.get(Rack, int(rack_val))
            if not rack:
                rack = db.scalars(
                    select(Rack).where(
                        Rack.site_id == site.id,
                        func.lower(Rack.name) == rack_val.lower(),
                    )
                ).first()
            if not rack:
                rack = Rack(
                    site_id=site.id,
                    location_id=location.id if location else None,
                    name=rack_val,
                )
                db.add(rack)
                db.flush()

        # Posizione Rack (U)
        rack_pos_raw = row_dict.get("rack_position", "").strip()
        rack_pos: int | None = None
        if rack_pos_raw and rack_pos_raw.isdigit():
            rack_pos = int(rack_pos_raw)
            if rack_pos < 1 or rack_pos > 60:
                rack_pos = None

        # 4. Produttore (Manufacturer)
        mfg_val = row_dict.get("manufacturer", "").strip()
        mfg: Manufacturer | None = None
        if mfg_val:
            mfg = db.scalars(
                select(Manufacturer).where(func.lower(Manufacturer.name) == mfg_val.lower())
            ).first()
            if not mfg:
                mfg = Manufacturer(name=mfg_val)
                db.add(mfg)
                db.flush()

        # 5. Modello (DeviceType)
        model_val = row_dict.get("model", "").strip()
        dev_type: DeviceType | None = None
        if model_val:
            if model_val.isdigit():
                dev_type = db.get(DeviceType, int(model_val))
            if not dev_type:
                dev_type = db.scalars(
                    select(DeviceType).where(func.lower(DeviceType.model) == model_val.lower())
                ).first()
            if not dev_type:
                if not mfg:
                    mfg = db.scalars(select(Manufacturer).order_by(Manufacturer.id)).first()
                    if not mfg:
                        mfg = Manufacturer(name="Generico")
                        db.add(mfg)
                        db.flush()
                dev_type = DeviceType(manufacturer_id=mfg.id, model=model_val, u_height=1)
                db.add(dev_type)
                db.flush()

        # 6. Ruolo (DeviceRole)
        role_val = row_dict.get("role", "").strip()
        role: DeviceRole | None = None
        if role_val:
            if role_val.isdigit():
                role = db.get(DeviceRole, int(role_val))
            if not role:
                role = db.scalars(
                    select(DeviceRole).where(func.lower(DeviceRole.name) == role_val.lower())
                ).first()
            if not role:
                r_lower = role_val.lower()
                lvl = 2
                col = "#888780"
                if "firewall" in r_lower or "gw" in r_lower or "router" in r_lower:
                    lvl, col = 0, "#e24b4b"
                elif "core" in r_lower:
                    lvl, col = 0, "#2b7fff"
                elif "distrib" in r_lower:
                    lvl, col = 1, "#4fa8f6"
                elif "access" in r_lower or "switch" in r_lower:
                    lvl, col = 2, "#10b981"
                elif "ap" in r_lower or "wifi" in r_lower:
                    lvl, col = 3, "#f59e0b"
                role = DeviceRole(name=role_val, level=lvl, color=col)
                db.add(role)
                db.flush()

        # 7. Stato
        status_val = row_dict.get("status", "").strip().lower()
        if status_val not in VALID_STATUSES:
            status_val = DeviceStatus.ACTIVE.value

        serial = row_dict.get("serial", "").strip() or None
        asset_tag = row_dict.get("asset_tag", "").strip() or None
        description = row_dict.get("description", "").strip() or None

        # Ricerca device esistente (per sede e nome)
        existing = db.scalars(
            select(Device).where(
                Device.site_id == site.id,
                func.lower(Device.name) == dev_name.lower(),
            )
        ).first()

        device: Device
        if existing:
            if not update_existing:
                skipped_devices.append(dev_name)
                continue
            # Aggiornamento campi
            existing.status = status_val
            if location:
                existing.location_id = location.id
            if rack:
                existing.rack_id = rack.id
            if rack_pos is not None:
                existing.rack_position = rack_pos
            if dev_type:
                existing.device_type_id = dev_type.id
            if role:
                existing.role_id = role.id
            if serial:
                existing.serial = serial
            if asset_tag:
                existing.asset_tag = asset_tag
            if description:
                existing.description = description
            device = existing
            updated_devices.append(dev_name)
        else:
            device = Device(
                name=dev_name,
                site_id=site.id,
                location_id=location.id if location else None,
                rack_id=rack.id if rack else None,
                rack_position=rack_pos,
                device_type_id=dev_type.id if dev_type else None,
                role_id=role.id if role else None,
                status=status_val,
                serial=serial,
                asset_tag=asset_tag,
                description=description,
            )
            db.add(device)
            db.flush()
            created_devices.append(dev_name)

        # 8. Assegnazione IP primario
        ip_val = row_dict.get("primary_ip", "").strip()
        if ip_val:
            try:
                norm_addr = normalize_ip_interface(ip_val)
                # Cerca un'interfaccia adatta o creane una 'mgmt'
                iface = db.scalars(
                    select(Interface).where(
                        Interface.device_id == device.id,
                        or_(
                            Interface.mgmt_only.is_(True),
                            Interface.name.in_(["mgmt", "Management", "eth0", "Gi1/0/1"]),
                        ),
                    ).order_by(Interface.mgmt_only.desc(), Interface.id)
                ).first()

                if not iface:
                    # Prendi la prima interfaccia qualunque del device
                    iface = db.scalars(
                        select(Interface).where(Interface.device_id == device.id).order_by(Interface.id)
                    ).first()

                if not iface:
                    # Crea una porta mgmt dedicata
                    iface = Interface(
                        device_id=device.id,
                        name="mgmt",
                        type=InterfaceType.COPPER.value,
                        mgmt_only=True,
                        description="Porta di management creata dall'import",
                    )
                    db.add(iface)
                    db.flush()

                # Cerca o crea l'indirizzo IP
                ip_net = ipaddress.ip_interface(norm_addr)
                host_str = str(ip_net.ip)

                ip_obj = db.scalars(
                    select(IPAddress).where(IPAddress.host == host_str)
                ).first()

                if ip_obj:
                    ip_obj.interface_id = iface.id
                    ip_obj.address = norm_addr
                    ip_obj.is_primary = True
                    ip_hook(db, ip_obj, {}, is_create=False)
                else:
                    ip_obj = IPAddress(
                        address=norm_addr,
                        interface_id=iface.id,
                        is_primary=True,
                    )
                    db.add(ip_obj)
                    db.flush()
                    ip_hook(db, ip_obj, {}, is_create=True)
            except Exception as exc:
                errors.append({
                    "row": row_index,
                    "device": dev_name,
                    "error": f"Errore configurazione IP '{ip_val}': {str(exc)}",
                })

    if dry_run:
        db.rollback()
    else:
        db.commit()

    return {
        "total_rows": row_index - 1,
        "created_count": len(created_devices),
        "updated_count": len(updated_devices),
        "skipped_count": len(skipped_devices),
        "errors": errors,
        "created_devices": created_devices,
        "updated_devices": updated_devices,
        "skipped_devices": skipped_devices,
        "dry_run": dry_run,
    }
