"""Server di posta nelle impostazioni (Amministrazione → Email), usato dai canali email."""
import smtplib

from app.services import mail
from tests.test_api import create


class FakeSMTP:
    """Al posto di smtplib.SMTP: ricorda server, accesso e messaggi."""
    sent: list = []

    def __init__(self, host, port, timeout=None):
        self.host, self.port, self.login_as = host, port, None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def starttls(self, context=None):
        pass

    def login(self, user, password):
        self.login_as = (user, password)

    def send_message(self, message):
        FakeSMTP.sent.append({"host": self.host, "port": self.port, "login": self.login_as,
                              "to": message["To"], "from": message["From"], "subject": message["Subject"]})


def test_server_di_posta_condiviso(client, monkeypatch):
    monkeypatch.setattr(mail.smtplib, "SMTP", FakeSMTP)
    FakeSMTP.sent = []
    assert client.get("/api/mail-settings").json()["host"] is None
    res = client.post("/api/alert-channels", json={"name": "Mail", "type": "email", "email_to": ["it@esempio.test"]})
    assert res.status_code == 422 and "server di posta" in res.json()["detail"]
    res = client.post("/api/alert-channels", json={"name": "Mail", "type": "email", "email_to": ["it@esempio.test"], "smtp_custom": True})
    assert res.status_code == 422 and "server SMTP" in res.json()["detail"]

    saved = client.put("/api/mail-settings", json={"host": " smtp.esempio.test ", "username": "netmap", "password": "segreta",
                                                     "sender": "netmap@esempio.test"}).json()
    assert saved["host"] == "smtp.esempio.test" and saved["has_password"] is True and "segreta" not in str(saved)
    common = create(client, "/alert-channels", {"name": "Mail", "type": "email", "email_to": ["it@esempio.test"]})
    own = create(client, "/alert-channels", {"name": "Reparto", "type": "email", "email_to": ["rep@esempio.test"],
                                             "smtp_custom": True, "smtp_host": "relay.esempio.test", "smtp_port": 2525})
    assert client.get("/api/mail-settings").json()["channels"] == 1
    assert client.get("/api/mail-settings").json()["custom_channels"] == 1

    assert client.post(f"/api/alert-channels/{common['id']}/test").json() == {"ok": True}
    assert client.post(f"/api/alert-channels/{own['id']}/test").json() == {"ok": True}
    assert FakeSMTP.sent[0] == {"host": "smtp.esempio.test", "port": 587, "login": ("netmap", "segreta"),
                                "to": "it@esempio.test", "from": "netmap@esempio.test", "subject": "NetMap: messaggio di prova"}
    assert FakeSMTP.sent[1]["host"] == "relay.esempio.test" and FakeSMTP.sent[1]["port"] == 2525
    assert FakeSMTP.sent[1]["login"] is None

    # password assente = invariata; il server non si toglie finché un canale lo usa
    client.put("/api/mail-settings", json={"host": "smtp2.esempio.test", "username": "netmap", "sender": None})
    assert client.get("/api/mail-settings").json()["has_password"] is True
    res = client.put("/api/mail-settings", json={"host": "", "username": None})
    assert res.status_code == 422
    assert client.put("/api/mail-settings", json={"host": "smtp2.esempio.test", "password": ""}).json()["has_password"] is False


def test_prova_del_server_di_posta(client, monkeypatch):
    monkeypatch.setattr(mail.smtplib, "SMTP", FakeSMTP)
    FakeSMTP.sent = []
    client.put("/api/mail-settings", json={"host": "smtp.esempio.test", "username": "netmap", "password": "segreta"})
    # impostazioni non salvate, password assente = quella salvata
    res = client.post("/api/mail-settings/test", json={"settings": {"host": "nuovo.esempio.test", "username": "netmap",
                                                                    "security": "none"}, "to": "io@esempio.test"})
    assert res.json() == {"ok": True, "message": None}
    assert FakeSMTP.sent[-1]["host"] == "nuovo.esempio.test" and FakeSMTP.sent[-1]["port"] == 25
    assert FakeSMTP.sent[-1]["login"] == ("netmap", "segreta")
    assert client.get("/api/mail-settings").json()["host"] == "smtp.esempio.test"  # niente salvato

    class Broken(FakeSMTP):
        def login(self, user, password):
            raise smtplib.SMTPAuthenticationError(535, b"bad credentials")

    monkeypatch.setattr(mail.smtplib, "SMTP", Broken)
    res = client.post("/api/mail-settings/test", json={"settings": {"host": "smtp.esempio.test", "username": "x"}, "to": "io@esempio.test"})
    assert res.json()["ok"] is False and res.json()["message"].startswith("Invio email non riuscito")
    assert client.post("/api/mail-settings/test", json={"settings": {"host": "x"}, "to": "nonvalido"}).status_code == 422
