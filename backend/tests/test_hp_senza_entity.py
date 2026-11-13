"""Switch HP "smart" (1810, 1820, 1910…): niente ENTITY-MIB e nomi delle porte con spazi doppi ("Port  1")."""
import copy

from app.discovery.vendors import model_from_descr
from app.services.topology import natural_key
from tests.snmp_devices import SW2
from tests.test_discovery import approve_all, device_named, pending, scan, setup  # noqa: F401

HP_1810_OID = "1.3.6.1.4.1.11.2.3.7.11.149"


def _hp_1810(port_name):
    """L'HP 2920 dei test vestito da 1810: sysDescr senza codice prodotto, niente ENTITY-MIB, porte "Port N"."""
    device = copy.deepcopy(SW2)
    device["system"] = {**device["system"], "name": "hp-ricevimento", "object_id": HP_1810_OID,
                        "descr": "HP 1810-24, PM.1.9, eCos-3.0, 1_12_8-customized-h"}
    device["entities"] = {}
    device["interfaces"] = {idx: (port_name(idx) if idx < 1000 else name, *rest)
                            for idx, (name, *rest) in device["interfaces"].items()}
    device["lldp_local"] = {num: (sub, port_name(int(pid)), d) for num, (sub, pid, d) in device["lldp_local"].items()}
    return device


def test_modello_dal_sysdescr():
    assert model_from_descr("HP 1810-24, PM.1.9, eCos-3.0, 1_12_8-customized-h") == "1810-24"
    assert model_from_descr("ProCurve J9450A Switch 1810G-24, P.1.14, eCos-2.0") == "J9450A"
    assert model_from_descr("HPE OfficeConnect Switch 1820 24G J9980A, PT.02.12") == "J9980A"
    assert model_from_descr("HP 1910-24G Switch Software Version 5.20") == "1910-24G"
    assert model_from_descr("Aruba Instant On 1930 24G 4SFP/SFP+ Switch JL682A, InstantOn_1930_2.4") == "JL682A"
    assert model_from_descr("Cisco IOS Software, C2960 Software") is None
    assert model_from_descr("Linux hp-server 5.10") is None
    assert model_from_descr(None) is None


def test_ordine_con_spazi_doppi():
    names = ["Port 10", "Port  1", "Port 26", "Port  9"]
    assert sorted(names, key=natural_key) == ["Port  1", "Port  9", "Port 10", "Port 26"]


def test_porte_e_modello_sistemati_dalla_scansione(client, setup, session_factory):
    # Com'era prima: modello chiamato con il sysObjectID e porte con gli spazi doppi
    hpe = client.post("/api/manufacturers", json={"name": "HPE"}).json()
    old_type = client.post("/api/device-types", json={"manufacturer_id": hpe["id"], "model": HP_1810_OID,
                                                      "sys_object_id": HP_1810_OID}).json()
    scan(client, session_factory, setup["job"]["id"], (_hp_1810(lambda n: f"Port {n:>2}"), "10.99.0.2"))
    approve_all(client)
    device = device_named(client, "hp-ricevimento")
    names = [p["name"] for p in client.get(f"/api/devices/{device['id']}/ports").json()]
    assert names[:3] == ["Port  1", "Port  2", "Port 49"]  # in ordine anche con gli spazi doppi

    # Scansione con i nomi ripuliti: le porte si rinominano in silenzio e il modello prende il nome vero
    scan(client, session_factory, setup["job"]["id"], (_hp_1810(lambda n: f"Port {n}"), "10.99.0.2"))
    assert pending(client) == []
    names = [p["name"] for p in client.get(f"/api/devices/{device['id']}/ports").json()]
    assert names[:3] == ["Port 1", "Port 2", "Port 49"]
    assert client.get(f"/api/device-types/{old_type['id']}").json()["model"] == "1810-24"


def test_modello_nuovo_con_il_nome_dal_sysdescr(client, setup, session_factory):
    scan(client, session_factory, setup["job"]["id"], (_hp_1810(lambda n: f"Port {n}"), "10.99.0.2"))
    [change] = [c for c in pending(client) if c["object_type"] == "device"]
    assert change["data"]["device_type"]["create"]["model"] == "1810-24"
