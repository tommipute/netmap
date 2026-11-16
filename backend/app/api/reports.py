"""Report: porte più cariche, errori, porte libere, PoE, disponibilità dei device."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.reports import AvailabilityReport, FreePortReport, PoeReport, PortErrorReport, PortUsageReport
from app.services import reports

router = APIRouter(prefix="/reports", tags=["Report"])
PORT_RANGE = Query("7d", pattern="^(1d|7d|30d)$", description="1d: punti da 5 minuti; 7d e 30d: da un'ora")


@router.get("/port-usage", response_model=PortUsageReport, summary="Porte più cariche: media, 95° percentile e picco")
def port_usage(range: str = PORT_RANGE, site_id: int | None = None,
               cabled: bool = Query(False, description="Solo porte con un cavo documentato verso un altro device"),
               db: Session = Depends(get_db)):
    return reports.port_usage(db, range, site_id, cabled)


@router.get("/port-errors", response_model=PortErrorReport, summary="Porte con errori o pacchetti scartati")
def port_errors(range: str = PORT_RANGE, site_id: int | None = None, db: Session = Depends(get_db)):
    return reports.port_errors(db, range, site_id)


@router.get("/free-ports", response_model=FreePortReport, summary="Porte libere per switch (giù da almeno N giorni)")
def free_ports(days: int = Query(30, ge=1, le=3650), site_id: int | None = None, db: Session = Depends(get_db)):
    return reports.free_ports(db, days, site_id)


@router.get("/poe", response_model=PoeReport, summary="Switch PoE: watt usati sul totale")
def poe(site_id: int | None = None, db: Session = Depends(get_db)):
    return reports.poe(db, site_id)


@router.get("/availability", response_model=AvailabilityReport, summary="Disponibilità dei device nel periodo")
def availability(range: str = Query("30d", pattern="^(7d|30d|1y)$"), site_id: int | None = None,
                 db: Session = Depends(get_db)):
    return reports.availability(db, range, site_id)
