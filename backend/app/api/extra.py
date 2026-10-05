from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Device, NetworkMap, Prefix
from app.schemas.ipam import IPAddressRead
from app.schemas.maps import MapRead, MapView, NodePosition
from app.schemas.views import (
    DeviceImportRequest,
    DeviceImportResult,
    Neighbor,
    Port,
    PrefixUtilization,
    SearchResult,
    Topology,
)
from app.services.device_import_export import (
    export_devices,
    generate_device_csv_template,
    import_devices_from_csv,
)
from app.services.ipam import available_ips, prefix_ip_addresses, prefix_utilization
from app.services.topology import (
    build_topology,
    device_neighbors,
    device_ports,
    global_search,
    map_view,
    save_map_positions,
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
