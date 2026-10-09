"""Avvisi quando i device smettono di rispondere e quando tornano."""
from datetime import datetime, timedelta, timezone

from app.models import AlertChannel, Device, Interface
from app.services import alerts
from app.services.alerts import AlertError, process_alerts
from tests.test_api import create

T0 = datetime(2026, 10, 7, 9, 0, tzinfo=timezone.utc)


def _devices(client, session_factory, names):
    site = create(client, "/sites", {"name": "Sede"})
    ids = [create(client, "/devices", {"name": n, "site_id": site["id"], "management_ip": f"10.9.0.{i + 1}/24"})["id"]
           for i, n in enumerate(names)]
    return ids


def _set(session_factory, ids, reachable, at):
    with session_factory() as db:
        for device_id in ids:
            device = db.get(Device, device_id)
            device.reachable, device.reachable_changed_at = reachable, at
        db.commit()


def test_avvisi_con_ritardo_raggruppati_e_ritorno(client, session_factory):
    channel = create(client, "/alert-channels", {"name": "Teams", "type": "webhook", "webhook_url": "https://esempio.test/hook", "delay_minutes": 5})
    sw1, sw2 = _devices(client, session_factory, ["sw-1", "sw-2"])
    sent = []
    fake = lambda ch, subject, text: sent.append((subject, text))  # noqa: E731

    _set(session_factory, [sw1, sw2], False, T0)
    with session_factory() as db:
        assert process_alerts(db, now=T0 + timedelta(minutes=2), sender=fake) == {"down": 0, "up": 0}  # troppo presto
        assert process_alerts(db, now=T0 + timedelta(minutes=6), sender=fake) == {"down": 2, "up": 0}
        assert process_alerts(db, now=T0 + timedelta(minutes=9), sender=fake) == {"down": 0, "up": 0}  # non si ripete
    assert len(sent) == 1 and sent[0][0] == "NetMap: 2 device non rispondono"
    assert "🔴 sw-1 (10.9.0.1) non risponde da 6 min · Sede" in sent[0][1]

    _set(session_factory, [sw1], True, T0 + timedelta(minutes=20))
    with session_factory() as db:
        assert process_alerts(db, now=T0 + timedelta(minutes=21), sender=fake) == {"down": 0, "up": 1}
    assert sent[1] == ("NetMap: sw-1 risponde di nuovo", "🟢 sw-1 (10.9.0.1) risponde di nuovo (giù per 21 min) · Sede")
    with session_factory() as db:
        assert db.get(AlertChannel, channel["id"]).last_error is None


def test_invio_fallito_si_riprova(client, session_factory):
    create(client, "/alert-channels", {"name": "Bot", "type": "telegram", "telegram_token": "123:abc", "telegram_chat_id": "-100", "delay_minutes": 0})
    (sw,) = _devices(client, session_factory, ["sw-x"])
    _set(session_factory, [sw], False, T0)

    def broken(ch, subject, text):
        raise AlertError("Servizio non raggiungibile")

    with session_factory() as db:
        assert process_alerts(db, now=T0, sender=broken)["down"] == 0
        assert db.query(AlertChannel).one().last_error == "Servizio non raggiungibile"
        assert process_alerts(db, now=T0 + timedelta(minutes=1), sender=lambda *a: None)["down"] == 1


def test_canali_segreti_e_prova(client, monkeypatch):
    res = client.post("/api/alert-channels", json={"name": "W", "type": "webhook", "webhook_url": "ftp://x"})
    assert res.status_code == 422
    res = client.post("/api/alert-channels", json={"name": "Mail", "type": "email", "email_to": ["it@esempio.test"]})
    assert res.status_code == 422 and "server SMTP" in res.json()["detail"]
    channel = create(client, "/alert-channels", {"name": "Teams", "type": "webhook", "webhook_url": "https://esempio.test/segreto"})
    assert channel["has_secret"] is True and "segreto" not in str(channel)

    calls = []
    monkeypatch.setitem(alerts.SENDERS, "webhook", lambda ch, subject, text: calls.append(subject))
    assert client.post(f"/api/alert-channels/{channel['id']}/test").json() == {"ok": True}
    assert calls == ["NetMap: messaggio di prova"]

    def broken(ch, subject, text):
        raise AlertError("Il servizio ha risposto 404: not found")

    monkeypatch.setitem(alerts.SENDERS, "webhook", broken)
    res = client.post(f"/api/alert-channels/{channel['id']}/test")
    assert res.status_code == 502 and "404" in res.json()["detail"]
    assert client.get(f"/api/alert-channels/{channel['id']}").json()["last_error"].startswith("Il servizio")


def test_avvisi_in_inglese(client, session_factory):
    create(client, "/alert-channels", {"name": "Teams EN", "type": "webhook", "webhook_url": "https://esempio.test/hook",
                                       "delay_minutes": 0, "language": "en"})
    (sw,) = _devices(client, session_factory, ["sw-en"])
    sent = []
    fake = lambda ch, subject, text: sent.append((subject, text))  # noqa: E731
    _set(session_factory, [sw], False, T0)
    with session_factory() as db:
        process_alerts(db, now=T0 + timedelta(minutes=95), sender=fake)
    assert sent == [("NetMap: sw-en not responding", "🔴 sw-en (10.9.0.1) not responding for 2 hours · Sede")]
    assert client.post("/api/alert-channels", json={"name": "X", "type": "webhook", "webhook_url": "https://x.test",
                                                    "language": "fr"}).status_code == 422


def test_render_toglie_le_parti_vuote():
    template = "🔴 {device} ({ip}) giù da {durata} · {sede} › {posizione} {sconosciuto}"
    assert alerts.render(template, {"device": "sw", "time": "5 min", "site": "Milano"}) == "🔴 sw giù da 5 min · Milano › {sconosciuto}"
    assert alerts.render("{device} ({ip}, {role})", {"device": "sw", "role": "Core"}) == "sw (, Core)"


def test_avvisi_solo_per_sede_ruolo_e_device_scelti(client, session_factory):
    milano = create(client, "/sites", {"name": "Milano"})
    roma = create(client, "/sites", {"name": "Roma"})
    edificio = create(client, "/locations", {"name": "Edificio", "site_id": milano["id"]})
    piano = create(client, "/locations", {"name": "Piano 1", "site_id": milano["id"], "parent_id": edificio["id"]})
    core = create(client, "/device-roles", {"name": "Core"})
    access = create(client, "/device-roles", {"name": "Accesso"})

    def device(name, site, role, location=None):
        return create(client, "/devices", {"name": name, "site_id": site["id"], "role_id": role["id"],
                                           "location_id": location and location["id"]})["id"]

    ids = {"mi-core": device("mi-core", milano, core, piano), "mi-acc": device("mi-acc", milano, access),
           "rm-core": device("rm-core", roma, core), "rm-acc": device("rm-acc", roma, access)}
    _set(session_factory, ids.values(), False, T0)

    def alerted(**scope):
        channel = create(client, "/alert-channels", {"name": f"C{len(scope)}{sorted(scope)}", "type": "webhook",
                                                     "webhook_url": "https://esempio.test/h", "delay_minutes": 0, **scope})
        sent = []
        with session_factory() as db:
            process_alerts(db, now=T0, sender=lambda ch, subject, text: ch.id == channel["id"] and sent.append(text))
        client.delete(f"/api/alert-channels/{channel['id']}")
        return sorted(line.split()[1] for line in sent[0].splitlines()) if sent else []

    assert alerted() == ["mi-acc", "mi-core", "rm-acc", "rm-core"]
    assert alerted(site_ids=[milano["id"]]) == ["mi-acc", "mi-core"]
    assert alerted(role_ids=[core["id"]]) == ["mi-core", "rm-core"]
    assert alerted(site_ids=[roma["id"]], role_ids=[core["id"]]) == ["rm-core"]  # dove e cosa insieme
    assert alerted(location_ids=[edificio["id"]]) == ["mi-core"]  # anche le posizioni contenute
    assert alerted(device_ids=[ids["rm-acc"]]) == ["rm-acc"]
    assert alerted(role_ids=[core["id"]], device_ids=[ids["rm-acc"]]) == ["mi-core", "rm-acc", "rm-core"]


def test_avvisi_delle_porte_e_modelli(client, session_factory):
    site = create(client, "/sites", {"name": "Sede"})
    sw = create(client, "/devices", {"name": "sw-1", "site_id": site["id"], "management_ip": "10.9.0.1/24"})
    core = create(client, "/devices", {"name": "core", "site_id": site["id"]})
    uplink = create(client, "/interfaces", {"device_id": sw["id"], "name": "Gi1/0/48", "description": "Uplink"})
    other = create(client, "/interfaces", {"device_id": core["id"], "name": "Te1/1/1"})
    free = create(client, "/interfaces", {"device_id": sw["id"], "name": "Gi1/0/1"})
    create(client, "/cables", {"a_interface_id": uplink["id"], "b_interface_id": other["id"]})
    res = client.post("/api/alert-channels", json={"name": "P", "type": "webhook", "webhook_url": "https://x.test", "ports": "selected"})
    assert res.status_code == 422 and "porta" in res.json()["detail"]
    channel = create(client, "/alert-channels", {
        "name": "Porte", "type": "webhook", "webhook_url": "https://esempio.test/h", "delay_minutes": 5, "ports": "cabled",
        "templates": {"port_down": "{porta} di {device} giù ({descrizione}) verso {collegata}", "up": "  "},
    })
    assert channel["templates"] == {"port_down": "{porta} di {device} giù ({descrizione}) verso {collegata}"}

    def set_ports(status, at, reachable=True):
        with session_factory() as db:
            device = db.get(Device, sw["id"])
            if device.reachable is not reachable:
                device.reachable, device.reachable_changed_at = reachable, T0
            for port_id in (uplink["id"], free["id"]):
                port = db.get(Interface, port_id)
                port.oper_status, port.oper_changed_at = status, at
            db.commit()

    sent = []
    fake = lambda ch, subject, text: sent.append((subject, text))  # noqa: E731
    set_ports("down", T0, reachable=False)
    with session_factory() as db:  # device giù: basta il suo avviso, le porte no
        process_alerts(db, now=T0 + timedelta(minutes=10), sender=fake)
    assert sent[-1] == ("NetMap: sw-1 non risponde", "🔴 sw-1 (10.9.0.1) non risponde da 10 min · Sede")
    set_ports("down", T0)
    with session_factory() as db:
        assert process_alerts(db, now=T0 + timedelta(minutes=11), sender=fake) == {"down": 1, "up": 1}
    assert sent[-2:] == [
        ("NetMap: sw-1 Gi1/0/48 giù", "Gi1/0/48 di sw-1 giù (Uplink) verso core Te1/1/1"),  # Gi1/0/1 non ha cavo
        ("NetMap: sw-1 risponde di nuovo", "🟢 sw-1 (10.9.0.1) risponde di nuovo (giù per 11 min) · Sede"),
    ]
    with session_factory() as db:
        port = db.get(Interface, uplink["id"])
        port.oper_status = "up"
        assert port.oper_changed_at > T0  # lo segna il modello quando lo stato cambia
        db.commit()
        assert process_alerts(db, now=T0 + timedelta(minutes=12), sender=fake) == {"down": 0, "up": 1}
    assert sent[-1] == ("NetMap: sw-1 Gi1/0/48 di nuovo su", "🟢 sw-1 Gi1/0/48 di nuovo su (giù per 12 min) · Sede")

    # Porte scelte: anche senza cavo
    client.patch(f"/api/alert-channels/{channel['id']}", json={"ports": "selected", "interface_ids": [free["id"]]})
    with session_factory() as db:
        assert process_alerts(db, now=T0 + timedelta(minutes=13), sender=fake) == {"down": 1, "up": 0}
    assert sent[-1][0] == "NetMap: sw-1 Gi1/0/1 giù"


def test_anteprima_dei_messaggi(client):
    res = client.post("/api/alert-messages/preview", json={"language": "it", "ports": "cabled",
                                                           "templates": {"down": "{device} giù · {ruolo} {nome}"}})
    assert res.status_code == 200
    preview = res.json()
    assert preview["down"] == {"subject": "NetMap: sw-piano1 non risponde, sw-piano1 Gi1/0/48 giù",
                               "text": "sw-piano1 giù · Accesso {nome}\n🔴 sw-piano1 Gi1/0/48 giù da 12 min (verso core-01 Te1/1/1)"
                                       " · Sede principale › Palazzina A › Piano 1"}
    assert preview["unknown"] == ["nome"]
    assert preview["defaults"]["down"].startswith("🔴 {device}")
    english = client.post("/api/alert-messages/preview", json={"language": "en"}).json()
    assert english["up"]["text"] == "🟢 sw-floor1 (10.0.1.20) responding again (down for 12 min) · Main site › Building A › Floor 1"
