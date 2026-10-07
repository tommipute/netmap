from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Device, NetworkMap, Prefix, Rack
from app.schemas.common import Page
from app.schemas.ipam import IPAddressRead
from app.schemas.maps import CableRoute, MapRead, MapView, NodePosition
from app.schemas.views import (
    CheckResult,
    DeviceImportRequest,
    DeviceImportResult,
    EndpointRead,
    Neighbor,
    Port,
    PrefixUtilization,
    RackElevation,
    SearchResult,
    StatusSummary,
    Topology,
)
from app.services.device_import_export import (
    export_devices,
    generate_device_csv_template,
    import_devices_from_csv,
)
from app.services.endpoints import endpoint_query, endpoint_rows
from app.services.ipam import available_ips, prefix_ip_addresses, prefix_utilization
from app.services.monitor import check_devices, status_summary
from app.services.topology import (
    build_topology,
    device_neighbors,
    device_ports,
    global_search,
    map_view,
    rack_elevation,
    save_map_positions,
    save_map_routes,
)

router = APIRouter()


def _get_or_404(db: Session, model, item_id: int):
    obj = db.get(model, item_id)
    if obj is None:
        raise HTTPException(404, "Elemento non trovato")
    return obj


# ---------- Device Import / Export ----------
@router.get("/devices/export", tags=["Device"], summary="Esporta device con relative informazioni (CSV o JSON)")
def get_devices_export(
    format: str = Query("csv", pattern="^(csv|json)$"),
    delimiter: str = Query(";", pattern="^([;,\\t])$"),
    site_id: int | None = None,
    location_id: int | None = None,
    rack_id: int | None = None,
    role_id: int | None = None,
    device_type_id: int | None = None,
    status: str | None = None,
    q: str | None = None,
    db: Session = Depends(get_db),
):
    content, media_type, filename = export_devices(
        db,
        format=format,
        delimiter=delimiter,
        site_id=site_id,
        location_id=location_id,
        rack_id=rack_id,
        role_id=role_id,
        device_type_id=device_type_id,
        status=status,
        q=q,
    )
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return Response(content=content, media_type=media_type, headers=headers)


@router.get("/devices/import/template", tags=["Device"], summary="Scarica modello CSV per importare device")
def get_device_import_template(
    delimiter: str = Query(";", pattern="^([;,\\t])$"),
):
    template = generate_device_csv_template(delimiter=delimiter)
    headers = {"Content-Disposition": 'attachment; filename="modello_import_device.csv"'}
    return Response(content=template, media_type="text/csv; charset=utf-8", headers=headers)


@router.post("/devices/import", response_model=DeviceImportResult, tags=["Device"], summary="Importa device da testo o file CSV")
def post_device_import(payload: DeviceImportRequest, db: Session = Depends(get_db)):
    db.info["audit_source"] = "import"  # storico delle modifiche
    return import_devices_from_csv(
        db,
        csv_text=payload.csv_data,
        update_existing=payload.update_existing,
        dry_run=payload.dry_run,
    )


# ---------- Device ----------
@router.get("/devices/{device_id}/ports", response_model=list[Port], tags=["Device"],
            summary="Porte del device con cosa c'è collegato")
def get_ports(device_id: int, db: Session = Depends(get_db)):
    _get_or_404(db, Device, device_id)
    return device_ports(db, device_id)



@router.get("/devices/{device_id}/neighbors", response_model=list[Neighbor], tags=["Device"],
            summary="Device collegati tramite cavo")
def get_neighbors(device_id: int, db: Session = Depends(get_db)):
    _get_or_404(db, Device, device_id)
    return device_neighbors(db, device_id)


# ---------- Prefissi ----------
@router.get("/prefixes/{prefix_id}/utilization", response_model=PrefixUtilization, tags=["Prefissi"],
            summary="Percentuale di utilizzo della subnet")
def get_utilization(prefix_id: int, db: Session = Depends(get_db)):
    return prefix_utilization(db, _get_or_404(db, Prefix, prefix_id))


@router.get("/prefixes/{prefix_id}/ip-addresses", response_model=list[IPAddressRead], tags=["Prefissi"],
            summary="IP registrati dentro la subnet")
def get_prefix_ips(prefix_id: int, db: Session = Depends(get_db)):
    ips = prefix_ip_addresses(db, _get_or_404(db, Prefix, prefix_id))
    return [IPAddressRead.model_validate(ip) for ip in ips]


@router.get("/prefixes/{prefix_id}/available-ips", response_model=list[str], tags=["Prefissi"],
            summary="Primi IP liberi della subnet")
def get_available_ips(prefix_id: int, limit: int = Query(10, ge=1, le=256), db: Session = Depends(get_db)):
    return available_ips(db, _get_or_404(db, Prefix, prefix_id), limit)


# ---------- Topologia e mappe ----------
@router.get("/topology", response_model=Topology, tags=["Topologia"],
            summary="Nodi e collegamenti di una sede/posizione")
def get_topology(site_id: int | None = None, location_id: int | None = None, db: Session = Depends(get_db)):
    return build_topology(db, site_id, location_id)


@router.get("/maps/{map_id}/view", response_model=MapView, tags=["Mappe"],
            summary="Device, posizioni salvate e cavi da disegnare")
def get_map_view(map_id: int, db: Session = Depends(get_db)):
    view = map_view(db, _get_or_404(db, NetworkMap, map_id))
    view["map"] = MapRead.model_validate(view["map"])
    return view


@router.put("/maps/{map_id}/routes", tags=["Mappe"],
            summary="Salva i punti di ancoraggio dei cavi disegnati a mano (sostituisce i precedenti)")
def put_map_routes(map_id: int, routes: list[CableRoute], db: Session = Depends(get_db)):
    return {"saved": save_map_routes(db, _get_or_404(db, NetworkMap, map_id), routes)}


@router.put("/maps/{map_id}/nodes", tags=["Mappe"],
            summary="Salva i device presenti in mappa e le loro posizioni (sostituisce le precedenti)")
def put_map_nodes(map_id: int, positions: list[NodePosition], db: Session = Depends(get_db)):
    saved = save_map_positions(db, _get_or_404(db, NetworkMap, map_id), positions)
    return {"saved": saved}


# ---------- Ricerca ----------
@router.get("/search", response_model=list[SearchResult], tags=["Ricerca"],
            summary="Cerca device, MAC address e IP")
def search(q: str = Query(..., min_length=2), db: Session = Depends(get_db)):
    return global_search(db, q)


# ---------- Fase 4: dov'è collegato, stato live, rack ----------
@router.get("/endpoints", response_model=Page[EndpointRead], tags=["Dov'è collegato"],
            summary="MAC visti nelle tabelle degli switch: cerca per MAC, IP o nome DNS")
def list_endpoints(
    q: str | None = Query(None, description="MAC (anche parziale o aabb.ccdd.eeff), inizio dell'IP o nome DNS"),
    device_id: int | None = Query(None, description="Switch"),
    interface_id: int | None = Query(None, description="Porta dello switch"),
    limit: int = Query(50, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    stmt = endpoint_query(q, device_id, interface_id)
    total = db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery()))
    items = list(db.scalars(stmt.limit(limit).offset(offset)).unique())
    return {"total": total, "items": endpoint_rows(db, items)}


@router.get("/status/summary", response_model=StatusSummary, tags=["Stato live"],
            summary="Quanti device rispondono, quanti no e quando è stato fatto l'ultimo controllo")
def get_status_summary(db: Session = Depends(get_db)):
    return status_summary(db)


@router.post("/devices/{device_id}/check", response_model=CheckResult, tags=["Stato live"],
             summary="Controlla subito il device (ping e SNMP sull'IP di management)")
def post_device_check(device_id: int, db: Session = Depends(get_db)):
    _get_or_404(db, Device, device_id)
    result = check_devices(db, [device_id])
    if result["checked"] == 0:
        raise HTTPException(422, "Il device non ha un IP di management oppure è pianificato o dismesso: niente da controllare")
    return result


@router.get("/racks/{rack_id}/elevation", response_model=RackElevation, tags=["Rack"],
            summary="Vista frontale: device del rack con unità occupate")
def get_rack_elevation(rack_id: int, db: Session = Depends(get_db)):
    return rack_elevation(db, _get_or_404(db, Rack, rack_id))
