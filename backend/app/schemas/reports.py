"""Report (services/reports.py)."""
from datetime import datetime

from pydantic import BaseModel, Field


class ReportDevice(BaseModel):
    device_id: int
    device_name: str
    site_id: int
    site: str
    location: str | None = None
    rack: str | None = None


class PortUsageRow(ReportDevice):
    interface_id: int
    interface_name: str
    description: str | None = None
    speed_mbps: int | None = None
    remote_device: str | None = Field(None, description="Altro capo del cavo documentato")
    remote_interface: str | None = None
    in_avg_bps: int | None = None
    out_avg_bps: int | None = None
    in_p95_bps: int | None = None
    out_p95_bps: int | None = None
    in_peak_bps: int | None = None
    out_peak_bps: int | None = None
    in_octets: int | None = None
    out_octets: int | None = None
    usage: float | None = Field(None, description="95° percentile più alto tra entrata e uscita / velocità (0-1)")
    saturated: bool = False


class PortUsageReport(BaseModel):
    range: str
    period: str
    saturated_at: float
    total: int
    saturated: int
    items: list[PortUsageRow]


class PortErrorRow(ReportDevice):
    interface_id: int
    interface_name: str
    description: str | None = None
    speed_mbps: int | None = None
    duplex: str | None = None
    errors: int
    discards: int
    last_at: datetime | None = Field(None, description="Ultimo intervallo con errori o scarti")


class PortErrorReport(BaseModel):
    range: str
    period: str
    total: int
    items: list[PortErrorRow]


class FreePortRow(ReportDevice):
    ports: int
    up: int
    down: int
    free: int = Field(description="Giù da almeno `days` giorni")
    free_ports: list[str]


class FreePortReport(BaseModel):
    days: int
    total: int
    ports: int
    free: int
    items: list[FreePortRow]


class PoeRow(ReportDevice):
    budget_w: int
    used_w: int | None = None
    usage: float | None = None
    delivering: int
    searching: int
    fault: int


class PoeReport(BaseModel):
    total: int
    budget_w: int
    used_w: int
    items: list[PoeRow]


class AvailabilityRow(ReportDevice):
    reachable: bool | None = None
    reachable_changed_at: datetime | None = None
    checks: int
    failed: int
    availability: float | None = Field(None, description="Controlli riusciti / controlli (0-1)")
    rtt_ms: float | None = None
    since: datetime | None = Field(None, description="Primo dato del periodo")


class AvailabilityReport(BaseModel):
    range: str
    period: str
    total: int
    items: list[AvailabilityRow]
