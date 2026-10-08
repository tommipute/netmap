"""Avvisi quando i device smettono di rispondere e quando tornano."""
from datetime import datetime, timedelta, timezone

from app.models import AlertChannel, Device
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
