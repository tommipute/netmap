"""Rame o fibra delle porte e tipo dei cavi dal modulo inserito (SFP, SFP+, QSFP), letto via SNMP."""
import copy

import pytest

from app.discovery.media import Media, media_from_text, media_hh3c
from tests.snmp_devices import SW1, SW2
from tests.test_discovery import (  # noqa: F401  (setup è una fixture)
    SW1_HOST, SW2_HOST, approve_all, device_named, diff_of, pending, ports_of, scan, setup,
)


# Testi veri di switch HPE Comware, Aruba/ProCurve e Cisco (tabelle dei moduli ed ENTITY-MIB)
@pytest.mark.parametrize("text, port, cable", [
    ("10G_BASE_SR_SFP", "fiber", "fiber_mm"),
    ("1000_BASE_LX_SFP", "fiber", "fiber_sm"),
    ("40G_BASE_SR4_QSFP_PLUS", "fiber", "fiber_mm"),
    ("1000LX", "fiber", "fiber_sm"),
    ("SFP+LR", "fiber", "fiber_sm"),
    ("SFP-10GBase-LR", "fiber", "fiber_sm"),
    ("SFP+ 10GBASE-SR", "fiber", "fiber_mm"),
    ("1000BaseSX SFP", "fiber", "fiber_mm"),
    ("HP J9989A 1000BASE-SX Port", "fiber", "fiber_mm"),
    ("SFP 10/25GE LR-S", "fiber", "fiber_sm"),
    ("QSFP 40GE SR4", "fiber", "fiber_mm"),
    ("QSFP 40GE CU1M", "copper", "dac"),
    ("SFP-10GBase-CX1", "copper", "dac"),
    ("QSFP 100GE AOC2M", "fiber", "fiber_mm"),
    ("10GBase-T SFP+", "copper", None),
    ("10/100/1000BaseTX SFP", "copper", None),
    ("HP J9987A 100/1000BASE-T Port", "copper", None),
    ("10300Mb/s-1310nm-LC-10km(0.009mm)", "fiber", "fiber_sm"),  # Huawei: "mm" è il diametro, non multimodale
    ("40Gb/s-850nm-MPO-100m(OM3 50um)", "fiber", "fiber_mm"),
    ("10000Mb/s-1200nm-Copper Pigtail-10m(0.05mm)", "copper", "dac"),
    ("Optics - 10GE LR 10km SFP+", "fiber", "fiber_sm"),
])
def test_rame_o_fibra_dal_testo(text, port, cable):
    assert media_from_text(text) == Media(port, cable, text)


@pytest.mark.parametrize("text", [None, "", "Aruba JL074y 10GIGBASE-GEN Port", "Transceiver(slot:1-port:8)",
                                  "LTE Adv WWAN NIM - Europe/North America Multimode LTE/DC-HSPA+/HSPA+/HSPA/UMTS",
                                  "TenGigabitEthernet1/1/1"])
def test_testi_che_non_dicono_niente(text):
    assert media_from_text(text) is None


def test_comware_dal_diametro_della_fibra():
    assert media_hh3c("MM", "10G_BASE_SR_SFP", 2) == Media("fiber", "fiber_mm", "10G_BASE_SR_SFP")
    # Tipo che non dice niente (cavo di stack): vale il diametro, 4 = rame
    assert media_hh3c(None, "SFP_PLUS_STACK", 4) == Media("copper", "dac", "SFP_PLUS_STACK")
    assert media_hh3c("UNKNOWN", None, 65535) is None


def test_porte_in_fibra_e_tipo_del_cavo(client, setup, session_factory):
    job_id = setup["job"]["id"]
    # Prima scansione senza moduli (come le versioni di prima): le porte Ethernet risultano in rame
    bare1, bare2 = copy.deepcopy(SW1), copy.deepcopy(SW2)
    bare1.pop("entity_ports"), bare2.pop("hp_transceivers")
    scan(client, session_factory, job_id, (bare1, SW1_HOST), (bare2, SW2_HOST))
    approve_all(client)
    scan(client, session_factory, job_id, (bare1, SW1_HOST), (bare2, SW2_HOST))
    approve_all(client)  # il cavo Te1/1/1 ↔ 49, senza tipo
    sw1, sw2 = device_named(client, "sw-sim-01"), device_named(client, "sw-sim-02")
    assert ports_of(client, sw1["id"])["Te1/1/1"]["type"] == "copper"
    cable = client.get("/api/cables").json()["items"][0]
    assert cable["type"] is None

    # Con i moduli: le porte create dalla scansione passano da sole alla fibra, il cavo senza tipo lo prende
    scan(client, session_factory, job_id, (SW1, SW1_HOST), (SW2, SW2_HOST))
    assert pending(client) == []
    assert client.get(f"/api/cables/{cable['id']}").json()["type"] == "fiber_mm"
    assert ports_of(client, sw1["id"])["Te1/1/1"]["type"] == "fiber"
    assert ports_of(client, sw2["id"])["49"]["type"] == "fiber"
    assert ports_of(client, sw1["id"])["Gi1/0/1"]["type"] == "copper"  # nessun modulo: resta com'è

    # Porta inserita a mano: il cambio di tipo si propone, non si fa da solo
    from app.models import Interface
    with session_factory() as db:
        port = db.get(Interface, ports_of(client, sw2["id"])["49"]["id"])
        port.source, port.type = "manual", "copper"
        db.commit()
    scan(client, session_factory, job_id, (SW1, SW1_HOST), (SW2, SW2_HOST))
    [change] = pending(client)
    assert diff_of(change)["Tipo"] == ["copper", "fiber"]
    approve_all(client)

    # Un tipo scritto a mano non si tocca
    client.patch(f"/api/cables/{cable['id']}", json={"type": "dac"})
    scan(client, session_factory, job_id, (SW1, SW1_HOST), (SW2, SW2_HOST))
    assert client.get(f"/api/cables/{cable['id']}").json()["type"] == "dac"
    assert pending(client) == []


def test_cavo_nuovo_con_il_tipo(client, setup, session_factory):
    job_id = setup["job"]["id"]
    scan(client, session_factory, job_id, (SW1, SW1_HOST), (SW2, SW2_HOST))
    approve_all(client)
    sw1 = device_named(client, "sw-sim-01")
    ports = ports_of(client, sw1["id"])
    assert (ports["Te1/1/1"]["type"], ports["Gi1/0/1"]["type"], ports["Po1"]["type"]) == ("fiber", "copper", "lag")
    scan(client, session_factory, job_id, (SW1, SW1_HOST), (SW2, SW2_HOST))
    [change] = pending(client)
    assert change["data"]["type"] == "fiber_mm"
    approve_all(client)
    assert client.get("/api/cables").json()["items"][0]["type"] == "fiber_mm"
