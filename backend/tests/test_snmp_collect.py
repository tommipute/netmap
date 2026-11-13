"""Test d'integrazione del collector SNMP contro agent simulati (snmpsim) su 127.0.0.1 e 127.0.0.2."""
import shutil
import socket
import subprocess
import tempfile
import time
from pathlib import Path

import pytest

from app.discovery.runner import summary
from app.discovery.snmp import Credentials, collect_all, probe_all
from tests.snmp_devices import SW1, SW2, SW3, host_data, snmprec_files

PORT = 11161
PORT_SW3 = 11162  # Cisco con le VLAN, sullo stesso indirizzo di sw1
V3 = dict(username="netmap", auth_protocol="sha", auth_key="authkey123", priv_protocol="aes", priv_key="privkey123")


def _wait_udp(address: str, port: int, timeout: float = 15.0) -> bool:
    """snmpsim risponde solo dopo aver indicizzato i dati: aspetto che una lettura vada a buon fine."""
    probe = Credentials(profile_id=0, name="probe", community="public", port=port, timeout=0.3, retries=0)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if collect_all([address], [probe]):
            return True
        time.sleep(0.3)
    return False


@pytest.fixture(scope="module")
def agents():
    if shutil.which("snmpsim-command-responder") is None:
        pytest.skip("snmpsim non installato (pip install -r requirements-dev.txt)")
    try:
        socket.socket(socket.AF_INET, socket.SOCK_DGRAM).bind(("127.0.0.2", 0))
    except OSError:
        pytest.skip("127.0.0.2 non disponibile su questo sistema")

    # snmpsim non gira come root e passa a 'nobody': la cartella dei dati deve essere leggibile da tutti
    # (quelle di tmp_path stanno sotto una cartella privata di root)
    base = Path(tempfile.mkdtemp(prefix="netmap-snmpsim-"))
    base.chmod(0o755)
    processes = []
    agents = (("sw1", SW1, "127.0.0.1", PORT), ("sw2", SW2, "127.0.0.2", PORT), ("sw3", SW3, "127.0.0.1", PORT_SW3))
    for name, device, address, port in agents:
        data_dir, cache_dir = base / name, base / f"{name}-cache"
        data_dir.mkdir(mode=0o755)
        cache_dir.mkdir()
        cache_dir.chmod(0o777)
        for file_name, content in snmprec_files(device, "public").items():
            (data_dir / file_name).write_text(content)
        args = [
            "snmpsim-command-responder", f"--data-dir={data_dir}", f"--cache-dir={cache_dir}",
            f"--agent-udpv4-endpoint={address}:{port}", "--process-user=nobody", "--process-group=nogroup",
            f"--v3-user={V3['username']}", f"--v3-auth-key={V3['auth_key']}", "--v3-auth-proto=SHA",
            f"--v3-priv-key={V3['priv_key']}", "--v3-priv-proto=AES",
        ]
        log = open(base / f"{name}.log", "w")
        processes.append(subprocess.Popen(args, stdout=log, stderr=subprocess.STDOUT))
    try:
        for name, _device, address, port in agents:
            if not _wait_udp(address, port):
                tail = (base / f"{name}.log").read_text()[-1500:]
                raise RuntimeError(f"snmpsim su {address} non risponde:\n{tail}")
        yield
    finally:
        for process in processes:
            process.terminate()
            process.wait(timeout=10)
        shutil.rmtree(base, ignore_errors=True)


def test_lettura_completa_dei_due_switch(agents):
    profiles = [
        Credentials(profile_id=1, name="sbagliato", community="nope", port=PORT, timeout=0.3, retries=0),
        Credentials(profile_id=2, name="giusto", community="public", port=PORT, timeout=1, retries=1),
    ]
    results = collect_all(["127.0.0.1", "127.0.0.2", "127.0.0.3"], profiles)  # .3 non risponde
    assert sorted(results, key=lambda r: r.host) == [
        host_data(SW1, "127.0.0.1", 2, "giusto"),
        host_data(SW2, "127.0.0.2", 2, "giusto"),
    ]


def test_snmp_v1(agents):
    creds = Credentials(profile_id=5, name="v1", version="v1", community="public", port=PORT, timeout=1, retries=1)
    assert collect_all(["127.0.0.1"], [creds]) == [host_data(SW1, "127.0.0.1", 5, "v1")]


def test_snmpv3_con_autenticazione_e_cifratura(agents):
    # snmpsim sceglie i dati dal context name, sui device veri di solito è vuoto
    creds = Credentials(profile_id=3, name="v3", version="v3", port=PORT, context="public", **V3)
    results = collect_all(["127.0.0.1"], [creds])
    assert [r.sys_name for r in results] == ["sw-sim-01.lab.local"]

    wrong = Credentials(profile_id=4, name="v3 sbagliato", version="v3", port=PORT, context="public", timeout=0.5,
                        retries=0, **{**V3, "auth_key": "chiavesbagliata"})
    assert collect_all(["127.0.0.1"], [wrong]) == []


def test_esito_di_ogni_indirizzo(agents):
    """Per gli indirizzi che non si leggono si sa perché: profilo per profilo, con il ping."""
    wrong_v2 = Credentials(profile_id=1, name="sbagliato", community="nope", port=PORT, timeout=0.3, retries=0)
    wrong_v3 = Credentials(profile_id=4, name="v3 sbagliato", version="v3", port=PORT, context="public", timeout=0.5,
                           retries=0, **{**V3, "auth_key": "chiavesbagliata"})
    wrong_user = Credentials(profile_id=6, name="v3 utente", version="v3", port=PORT, context="public", timeout=0.5,
                             retries=0, **{**V3, "username": "nessuno"})
    probes = {p.host: p for p in probe_all(["127.0.0.1", "127.0.0.3"], [wrong_v2, wrong_v3, wrong_user])}

    sw1 = probes["127.0.0.1"]
    assert sw1.data is None and sw1.pinged
    assert [(a.profile, a.answered) for a in sw1.attempts] == [
        ("sbagliato", False), ("v3 sbagliato", True), ("v3 utente", True)]
    assert sw1.attempts[0].error.startswith("nessuna risposta (community sbagliata")
    assert "password di autenticazione" in sw1.attempts[1].error
    assert "utente SNMPv3 sconosciuto" in sw1.attempts[2].error

    lines = summary(list(probes.values()))
    assert any(line.startswith("Rispondono con un errore (profilo v3 sbagliato: password") and "127.0.0.1" in line
               for line in lines)

    right = Credentials(profile_id=2, name="giusto", community="public", port=PORT, timeout=1, retries=0)
    [ok] = probe_all(["127.0.0.2"], [wrong_v2, right])
    assert ok.data.sys_name and ok.data.problems == []
    assert [(a.profile, a.error) for a in ok.attempts][1] == ("giusto", None)


def test_cisco_tabella_mac_per_vlan(agents):
    """Cisco: con la community normale solo la VLAN 1, le altre con public@VLAN (SNMPv3: context vlan-N).
    Si leggono solo le VLAN usate da qualche porta (la 30 no: non ha il file e farebbe un problema)."""
    expected = host_data(SW3, "127.0.0.1", 7, "cisco")
    assert {e.vlan for e in expected.fdb} == {1, 10, 20}
    for version, extra in (("v2c", {"community": "public"}), ("v1", {"community": "public"}),
                           ("v3", {"context": "public", **V3})):
        creds = Credentials(profile_id=7, name="cisco", version=version, port=PORT_SW3, timeout=1, retries=1, **extra)
        [probe] = probe_all(["127.0.0.1"], [creds])
        assert probe.data.problems == [], version
        assert probe.data == expected, version


def test_cisco_senza_community_per_vlan(agents, monkeypatch):
    """Se lo switch non risponde a community@VLAN si tiene la VLAN 1, c'è un solo problema (senza la community) e
    non si provano le altre VLAN."""
    from app.discovery import snmp
    # snmpsim risponderebbe anche a public@30 (ripiega su un altro file): la VLAN 30 la faccio chiedere con una
    # community che non conosce, come uno switch che non permette la lettura per VLAN
    real_replace = snmp.replace
    monkeypatch.setattr(snmp, "replace", lambda creds, **changes: real_replace(
        creds, **{k: "segreta@30" if v == "public@30" else v for k, v in changes.items()}))
    monkeypatch.setattr(snmp, "cisco_fdb_vlans", lambda names, untagged, tagged: [30, 10])
    creds = Credentials(profile_id=7, name="cisco", community="public", port=PORT_SW3, timeout=0.3, retries=0)
    [probe] = probe_all(["127.0.0.1"], [creds])
    assert {e.vlan for e in probe.data.fdb} == {1}
    assert len(probe.data.problems) == 1
    assert probe.data.problems[0].startswith("tabella MAC della VLAN 30: nessuna risposta")
    assert "segreta" not in probe.data.problems[0]
