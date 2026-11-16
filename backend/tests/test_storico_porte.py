"""Storico delle porte: campioni dai contatori, righe da 5 minuti, ora e giorno, pulizia e grafico."""
import asyncio
import copy
from datetime import datetime, timedelta, timezone

from app.lab.snmprec import snmprec
from app.services import port_stats
from app.services.monitor import Details, PortDetail, Probe, check_devices, read_details
from tests.snmp_devices import SW1
from tests.test_porte_dettagli import FakeSession, device_with_ports, set_if_index

HC_IN, HC_OUT = (1, 3, 6, 1, 2, 1, 31, 1, 1, 1, 6), (1, 3, 6, 1, 2, 1, 31, 1, 1, 1, 10)
IN_32 = (1, 3, 6, 1, 2, 1, 2, 2, 1, 10)


def test_differenza_dei_contatori():
    assert port_stats.counter_delta(150, 100) == 50
    assert port_stats.counter_delta(None, 100) is None and port_stats.counter_delta(100, None) is None
    # 32 bit che ha fatto il giro: si conta; un contatore che riparte da poco (switch riavviato) no
    assert port_stats.counter_delta(100, 2 ** 32 - 100, port_stats.WRAP_32) == 200
    assert port_stats.counter_delta(100, 5000, port_stats.WRAP_32) is None
    assert port_stats.counter_delta(100, 2 ** 64 - 100, 2 ** 64) is None


def test_intervalli():
    moment = datetime(2026, 11, 16, 10, 47, 31, tzinfo=timezone.utc)
    assert port_stats.bucket(moment, "5m") == datetime(2026, 11, 16, 10, 45, tzinfo=timezone.utc)
    assert port_stats.bucket(moment, "1h") == datetime(2026, 11, 16, 10, tzinfo=timezone.utc)
    day = port_stats.bucket(moment, "1d").astimezone()  # mezzanotte dell'ora locale del server
    assert (day.hour, day.minute) == (0, 0) and day <= moment < day + timedelta(days=1, hours=1)


def test_lettura_dei_byte():
    device = copy.deepcopy(SW1)
    device["traffic"] = {1: (1000, 500)}
    session = FakeSession(snmprec(device))
    assert session.data[HC_IN + (1,)] == 1_000_000  # valore di partenza del contatore che varia
    details = asyncio.run(read_details(session))
    assert details.ports[1].octets == (1_000_000, 500_000, 2 ** 64)
    assert details.ports[2].octets is None

    device["traffic_32bit"] = True  # switch vecchio: solo ifInOctets/ifOutOctets
    session = FakeSession(snmprec(device))
    assert HC_IN + (1,) not in session.data and session.data[IN_32 + (1,)] == 1_000_000
    assert asyncio.run(read_details(session)).ports[1].octets == (1_000_000, 500_000, 2 ** 32)


def test_monitor_salva_lo_storico(client, session_factory):
    from app.models import Device, Interface, PortStat
    device, ports = device_with_ports(client)
    set_if_index(session_factory, ports)
    first, second = ports["Gi1/0/1"]["id"], ports["Gi1/0/2"]["id"]
    details = Details(ports={1: PortDetail("up", errors=(0, 0, 0, 0), octets=(1000, 2000, 2 ** 64)),
                             2: PortDetail("down", errors=(0, 0, 0, 0))})
    probe = {device["id"]: Probe(reachable=True, oper_status={1: "up", 2: "down", 3: "down"}, details=details)}

    def read(octets, errors=(0, 0, 0, 0), ago=timedelta(minutes=5)):
        details.ports[1] = PortDetail("up", errors=errors, octets=(*octets, 2 ** 64))
        with session_factory() as db:
            db.get(Device, device["id"]).ports_polled_at = datetime.now(timezone.utc) - ago
            db.commit()
            check_devices(db, prober=lambda targets: probe)

    with session_factory() as db:  # prima lettura: solo il punto di partenza
        check_devices(db, prober=lambda targets: probe)
        assert db.query(PortStat).count() == 0
        assert db.get(Interface, first).in_octets == 1000 and db.get(Interface, first).in_bps is None

    read((1000 + 300 * 1000, 2000 + 300 * 250), errors=(2, 0, 1, 0))  # 1000 byte/s in, 250 out in 5 minuti
    with session_factory() as db:
        iface = db.get(Interface, first)
        assert (iface.in_bps, iface.out_bps) == (8000, 2000)
        rows = {(r.interface_id, r.period): r for r in db.query(PortStat)}
        assert set(rows) == {(i, p) for i in (first, second) for p in port_stats.PERIODS}
        row = rows[first, "5m"]
        assert (row.seconds, row.in_octets, row.out_octets, row.errors, row.discards, row.up_seconds) == (300, 300_000, 75_000, 2, 1, 300)
        assert rows[second, "1h"].in_octets is None and rows[second, "1h"].up_seconds == 0  # giù, senza contatori

    # Contatori ripartiti (switch riavviato): nessun traffico per questa lettura, ma si riparte da lì
    read((500, 500))
    with session_factory() as db:
        assert db.get(Interface, first).in_bps is None and db.get(Interface, first).in_octets == 500
    # Monitor fermo per un'ora: i contatori servono di nuovo solo da partenza
    read((500 + 3600 * 2000, 500), ago=timedelta(hours=1))
    with session_factory() as db:
        assert db.get(Interface, first).in_bps is None

    # Il grafico: un punto (o due se le letture sono cadute a cavallo dei 5 minuti) con la media in bit/s
    data = client.get(f"/api/interfaces/{first}/stats", params={"range": "1d"}).json()
    assert data["period"] == "5m" and data["step"] == 300 and data["in_octets"] == 300_000
    assert data["errors"] == 2 and data["discards"] == 1 and data["up"] == 1
    assert sum(p["in_bps"] or 0 for p in data["points"]) >= 8000
    assert client.get(f"/api/interfaces/{first}/stats", params={"range": "2h"}).status_code == 422
    assert client.get("/api/interfaces/999999/stats").status_code == 404


def test_righe_e_pulizia(session_factory, client):
    from app.models import PortStat
    _, ports = device_with_ports(client)
    port = ports["Gi1/0/1"]["id"]
    now = datetime(2026, 11, 16, 10, 2, tzinfo=timezone.utc)
    with session_factory() as db:
        # Due letture nello stesso intervallo da 5 minuti, una nel successivo: 2 righe da 5 minuti, 1 per ora e giorno
        for minutes, octets, poe in ((0, 30_000, 4000), (1, 60_000, 6000), (6, 30_000, None)):
            sample = port_stats.Sample(port, 60, in_octets=octets, out_octets=0, up=True, poe_mw=poe)
            port_stats.record(db, [sample], now + timedelta(minutes=minutes))
        db.commit()
        hour = db.query(PortStat).filter_by(period="1h").one()
        assert (hour.seconds, hour.in_octets, hour.in_peak_bps, hour.poe_mws) == (180, 120_000, 8000, 600_000)
        assert db.query(PortStat).filter_by(period="5m").count() == 2

        data = port_stats.series(db, port, "1d", now=now + timedelta(minutes=10))
        assert [p["in_bps"] for p in data["points"]] == [6000, 4000]
        assert data["points"][0]["poe_w"] == 5.0 and data["points"][1]["poe_w"] is None
        assert data["in_octets"] == 120_000 and data["up"] == 1

        # Pulizia: i 5 minuti durano 2 giorni, le ore 30, i giorni un anno
        assert port_stats.prune(db, now + timedelta(days=3)) == 2
        assert port_stats.prune(db, now + timedelta(days=31)) == 1
        assert db.query(PortStat).count() == 1
        assert port_stats.prune(db, now + timedelta(days=367)) == 1
