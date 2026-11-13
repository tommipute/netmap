"""Stranezze di switch di altre marche, viste sulle registrazioni SNMP di molti produttori: dati costruiti a mano."""
import asyncio
import copy
from collections import Counter

from app.discovery import snmp
from app.discovery.vendors import model_from_text
from app.models import SnmpReport
from tests.snmp_devices import SW2
from tests.test_discovery import approve_all, device_named, pending, scan, setup  # noqa: F401

MAC = (0x00, 0x50, 0x56, 0x00, 0x00, 0x10)


class FakeSession:
    """Solo `walk`: {OID della colonna: {indice: valore}}."""

    def __init__(self, tables):
        self.tables, self.section, self.problems, self.notes, self.fdb_unmapped = tables, "", [], Counter(), []

    async def walk(self, oid):
        return dict(self.tables.get(oid, {}))


def run(coro):
    return asyncio.run(coro)


def test_modello_dalla_descrizione_di_sistema():
    cases = {
        "Cisco Internetwork Operating System Software IOS (tm) C3750 Software (C3750-IPSERVICESK9-M)": "C3750",
        "S5720-56C-PWR-EI-AC\nHuawei Versatile Routing Platform Software \r\n VRP (R) software,Version 5.170 "
        "(S5720 V200R010C00SPC600) \r\n Copyright (C) 2007 Huawei Technologies Co., Ltd.": "S5720-56C-PWR-EI-AC",
        "Huawei Versatile Routing Platform Software VRP (R) software, Version 5.170 (S5720 V200R011C10SPC500)": "S5720",
        "ExtremeXOS (X480-24x) version 15.3.5.2 v1535b2 by release-manager": "X480-24x",
        "GS1900-48": "GS1900-48",
        "RouterOS RB760iGS": "RB760iGS",
        "Arista Networks EOS version 4.24.2F running on an Arista Networks DCS-7280SR2A-48YC6-M": "DCS-7280SR2A-48YC6-M",
    }
    for text, model in cases.items():
        assert model_from_text(text) == model, text
    # Niente modello: versioni, porte, processori, date
    for text in ("Linux 5.10.0-21-amd64 #1 SMP x86_64", "24-port 10/100/1000 Switch, 4 SFP, firmware v1.2.3",
                 "Software Version 8.3.1, built 08-Sep-2009", "Ethernet Switch Layer2+ 802.1Q", None, ""):
        assert model_from_text(text) is None, text


def test_modello_dalla_descrizione_dello_chassis():
    session = FakeSession({
        snmp.ENT_PHYSICAL_CLASS: {(1,): 3, (2,): 10},
        snmp.ENT_PHYSICAL_SERIAL: {(1,): b"21023529"},
        snmp.ENT_PHYSICAL_MODEL: {(1,): b""},
        snmp.ENT_PHYSICAL_DESCR: {(1,): b"S5720-28X-LI-AC Routing Switch"},
    })
    serial, model, members, hint = run(snmp._chassis(session))
    assert (serial, model, members, hint) == ("21023529", None, [], "S5720-28X-LI-AC")


def test_indice_mac_con_la_lunghezza_davanti():
    assert snmp._mac_from_index(MAC) == "00:50:56:00:00:10"
    assert snmp._mac_from_index((6, *MAC)) == "00:50:56:00:00:10"
    assert snmp._mac_from_index((5, *MAC)) is None

    session = FakeSession({
        snmp.DOT1Q_TP_FDB_PORT: {(10, 6, *MAC): 1},
        snmp.DOT1Q_TP_FDB_STATUS: {(10, 6, *MAC): 3},
    })
    fdb, _pvids, qbridge = run(snmp._bridge(session, {1: 101}, {}))
    assert qbridge
    assert fdb == [snmp.FdbEntry(mac="00:50:56:00:00:10", if_index=101, vlan=10)]
    assert session.notes == {"mac_length_prefix": 1}  # per la scheda "Cosa ho letto"


def test_porta_bridge_uguale_all_ifindex_se_manca_la_tabella():
    with_pvid = FakeSession({snmp.DOT1Q_PVID: {(1,): 10, (2,): 20}})
    assert run(snmp._base_ports(with_pvid, [1, 2, 3])) == {1: 1, 2: 2, 3: 3}
    assert with_pvid.notes == {"bridge_port_ifindex": 1}
    # Niente tabelle del bridge: lo switch non fa da bridge, nessuna porta
    assert run(snmp._base_ports(FakeSession({}), [1, 2, 3])) == {}
    # Con dot1dBasePortIfIndex vale quella
    mapped = FakeSession({snmp.DOT1D_BASE_PORT_IF_INDEX: {(1,): 1001}, snmp.DOT1Q_PVID: {(1,): 10}})
    assert run(snmp._base_ports(mapped, [1001])) == {1: 1001}


def test_mac_imparati_su_un_aggregato():
    """Avaya/Extreme: per un MAC visto su un LAG la porta è l'ifIndex del LAG, non una porta bridge."""
    other = (0x00, 0x50, 0x56, 0x00, 0x00, 0x20)
    session = FakeSession({snmp.DOT1D_TP_FDB_PORT: {MAC: 1, other: 6145, (0, 1, 2, 3, 4, 5): 999}})
    rows = run(snmp._dot1d_fdb(session, {1: 1}, {6145}))
    assert sorted(rows) == [("00:50:56:00:00:10", 1), ("00:50:56:00:00:20", 6145)]  # 999 non è nulla: scartata
    assert session.notes == {"fdb_on_lag": 1, "fdb_unmapped": 1}
    assert session.fdb_unmapped == [("00:01:02:03:04:05", 999, None)]  # per le regole SNMP
    session.notes.clear()
    # Senza sapere che 6145 è un LAG la riga resta fuori
    assert run(snmp._dot1d_fdb(session, {1: 1})) == [("00:50:56:00:00:10", 1)]


def _porte_omonime():
    """L'HP dei test con porte che hanno lo stesso nome: uguali in tutto (Huawei, Dell, SLX) o con ifDescr diversi
    (ProCurve, due "lo0"). Nel database il nome è unico per device."""
    device = copy.deepcopy(SW2)
    device["system"] = {**device["system"], "name": "sw-omonime"}
    device["interfaces"][60] = ("mgmt", "mgmt", 6, 1500, 1000, "00:22:33:44:55:3c", 1, 1, "")
    device["interfaces"][61] = ("mgmt", "mgmt", 6, 1500, 1000, "00:22:33:44:55:3d", 1, 2, "")
    device["interfaces"][70] = ("lo0", "Switch loopback interface", 24, 1500, None, "", 1, 1, "")
    device["interfaces"][71] = ("lo0", "Out Of Band Management loopback Interface", 24, 1500, None, "", 1, 1, "")
    return device


def test_porte_con_lo_stesso_nome(client, setup, session_factory):
    scan(client, session_factory, setup["job"]["id"], (_porte_omonime(), "10.99.0.2"))
    approve_all(client)
    device = device_named(client, "sw-omonime")
    ports = {p["name"] for p in client.get(f"/api/devices/{device['id']}/ports").json()}
    assert {"mgmt", "mgmt (61)", "lo0", "Out Of Band Management loopback Interface"} <= ports

    # Alla scansione dopo non c'è niente da proporre: ogni porta si ritrova
    scan(client, session_factory, setup["job"]["id"], (_porte_omonime(), "10.99.0.2"))
    assert [c for c in pending(client) if c["object_type"] == "interface"] == []


def test_resoconto_della_lettura(client, setup, session_factory):
    """Scheda "Cosa ho letto": il resoconto del device nuovo passa al device approvandolo e si aggiorna."""
    scan(client, session_factory, setup["job"]["id"], (_porte_omonime(), "10.99.0.2"))
    with session_factory() as db:
        [report] = db.query(SnmpReport).all()
        assert report.device_id is None and report.host == "10.99.0.2"
    approve_all(client)
    device = device_named(client, "sw-omonime")
    read = client.get(f"/api/devices/{device['id']}/snmp-report").json()
    data = read["data"]
    assert data["host"] == "10.99.0.2" and data["model"] == "J9728A" and data["serial"] == "SGSIM0002"
    assert data["counts"]["interfaces"] == 8 and data["counts"]["fdb"] == 3 and data["counts"]["lldp"] == 1
    assert data["notes"] == {"renamed_ports": 2}  # "mgmt (61)" e la descrizione del secondo lo0
    assert data["manufacturer"] == "HPE"

    # Scansione dopo: stesso resoconto aggiornato, nessuno nuovo
    first_run = read["run_id"]
    scan(client, session_factory, setup["job"]["id"], (_porte_omonime(), "10.99.0.2"))
    assert client.get(f"/api/devices/{device['id']}/snmp-report").json()["run_id"] != first_run
    with session_factory() as db:
        assert db.query(SnmpReport).count() == 1


def test_resoconto_assente(client, setup):
    device = client.post("/api/devices", json={"name": "a-mano", "site_id": setup["site"]["id"]}).json()
    assert client.get(f"/api/devices/{device['id']}/snmp-report").json() is None


def test_mac_con_un_numero_dopo_l_indirizzo():
    """Zyxel IES: indice MAC.numero invece di 6.MAC; il formato si decide per tutta la tabella."""
    session = FakeSession({snmp.DOT1D_TP_FDB_PORT: {(*MAC, 1): 1, (0x00, 0x50, 0x56, 0x00, 0x00, 0x20, 0): 2}})
    rows = run(snmp._dot1d_fdb(session, {1: 1, 2: 2}))
    assert sorted(rows) == [("00:50:56:00:00:10", 1), ("00:50:56:00:00:20", 2)]
    assert session.notes == {"fdb_index_suffix": 2}


def test_mac_dalla_colonna_degli_indirizzi():
    """Netonix: righe numerate 1, 2, 3… e il MAC solo nella colonna dot1dTpFdbAddress."""
    session = FakeSession({
        snmp.DOT1D_TP_FDB_PORT: {(1,): 1, (2,): 2},
        snmp.DOT1D_TP_FDB_ADDRESS: {(1,): bytes(MAC), (2,): b"\x00\x50\x56\x00\x00\x20"},
    })
    assert sorted(run(snmp._dot1d_fdb(session, {1: 1, 2: 2}))) == [("00:50:56:00:00:10", 1), ("00:50:56:00:00:20", 2)]
    assert session.notes == {"fdb_address_column": 2}


def test_lldp_con_l_indice_accorciato():
    """TP-Link JetStream: porta locale.indice senza timeMark; RouterOS 6: solo l'indice del vicino."""
    interfaces = [snmp.IfData(if_index=5, name="gi5", descr="gi5")]
    session = FakeSession({
        snmp.LLDP_REM_CHASSIS_ID_SUBTYPE: {(5, 1): 4, (7,): 4},
        snmp.LLDP_REM_CHASSIS_ID: {(5, 1): bytes(MAC), (7,): b"\x00\x50\x56\x00\x00\x20"},
        snmp.LLDP_LOC_PORT_ID_SUBTYPE: {(5,): 5},
        snmp.LLDP_LOC_PORT_ID: {(5,): b"gi5"},
    })
    neighbors = run(snmp._lldp(session, interfaces))
    assert [(n.chassis_mac, n.local_if_index, n.rem_index) for n in neighbors] == [
        ("00:50:56:00:00:10", 5, 1), ("00:50:56:00:00:20", None, 7)]
    assert session.notes == {"lldp_short_index": 2}


def test_porta_locale_lldp_con_l_ifindex_come_id():
    """Alcatel-Lucent AOS 7: lldpLocPortNum 2083 ha come ID locale "101035", l'ifIndex della porta 2/1/35."""
    interfaces = [snmp.IfData(if_index=101035, name="2/1/35", descr="GNI 2/1/35"),
                  snmp.IfData(if_index=49, name="49", descr="49")]
    notes = Counter()
    local = snmp._lldp_local_ports(interfaces, {(2083,): 7, (101,): 7}, {(2083,): b"101035", (101,): b"49"}, {}, notes)
    assert local == {2083: 101035, 101: 49}  # "49" è prima di tutto il nome di una porta
    assert notes == {"lldp_local_ifindex": 1}
