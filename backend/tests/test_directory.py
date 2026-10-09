"""Accesso con Active Directory, con una directory finta al posto del domain controller."""
import re
from types import SimpleNamespace

import pytest

from app.models import DirectorySettings
from app.services import directory
from tests.test_discovery import create

BASE = "DC=prova,DC=lan"
GROUPS = {name: f"CN={name},CN=Users,{BASE}" for name in ("NetMap-Admin", "NetMap-Editor", "NetMap-Viewer", "Tecnici")}
SETTINGS = {
    "enabled": True, "servers": "dc1.prova.lan, dc2.prova.lan", "security": "ldaps", "domain": "prova.lan",
    "admin_group": "NetMap-Admin", "editor_group": "NetMap-Editor", "viewer_group": "NetMap-Viewer",
}


class FakeDirectory:
    """Utenti e gruppi del dominio finto; `down` = nessun domain controller risponde."""

    def __init__(self):
        self.down = False
        self.binds = []
        self.users = {
            "mario.rossi": {"password": "Mario-2026", "name": "Mario Rossi", "groups": {"NetMap-Admin"}},
            "luca.bianchi": {"password": "Luca-2026", "name": "Luca Bianchi", "groups": {"Tecnici"}, "ou": "OU=Sede"},
            "anna.verdi": {"password": "Anna-2026", "name": "Anna Verdi", "groups": set()},
            "ex.dipendente": {"password": "Ex-2026", "name": "Ex", "groups": {"NetMap-Viewer"}, "disabled": True},
        }
        self.nested = {"Tecnici": {"NetMap-Editor"}}  # Tecnici è membro di NetMap-Editor

    def dn(self, sam):
        return f"CN={self.users[sam]['name']},{self.users[sam].get('ou', 'CN=Users')},{BASE}"

    def member_of(self, sam):
        found, todo = set(), list(self.users[sam]["groups"])
        while todo:
            group = todo.pop()
            if group not in found:
                found.add(group)
                todo.extend(self.nested.get(group, ()))
        return {GROUPS[g] for g in found}


class FakeSession:
    def __init__(self, fake: FakeDirectory, cfg):
        if fake.down:
            raise directory.DirectoryError("Nessun domain controller risponde (dc1.prova.lan): controlla nome, porta e firewall")
        self.fake, self.cfg = fake, cfg

    def bind(self, name, password):
        assert password, "mai un bind con la password vuota"
        self.fake.binds.append(name)
        sam = name.split("\\")[-1].split("@")[0].lower()
        user = self.fake.users.get(sam)
        if user is None or user["password"] != password:
            return False
        if user.get("disabled"):
            raise directory.LoginDenied(directory.BIND_REASONS["533"])
        return True

    def find_user(self, filter_):
        sam = re.search(r"sAMAccountName=([^)]+)", filter_).group(1).lower()
        if sam not in self.fake.users:
            return None
        # In AD il nome può avere le maiuscole: in NetMap diventa minuscolo
        values = {"sAMAccountName": sam.title() if sam == "mario.rossi" else sam, "displayName": self.fake.users[sam]["name"]}
        return _Entry(self.fake.dn(sam), values)

    def group_dn(self, group):
        return group if "=" in group else GROUPS.get(group)

    def is_member(self, user_dn, group_dn):
        sam = next(s for s in self.fake.users if self.fake.dn(s) == user_dn)
        return group_dn in self.fake.member_of(sam)

    def close(self):
        pass


class _Entry:
    def __init__(self, dn, values):
        self.entry_dn, self.values = dn, values

    def __getitem__(self, name):
        if name not in self.values:
            raise KeyError(name)
        return SimpleNamespace(value=self.values[name])


@pytest.fixture()
def ad(monkeypatch):
    fake = FakeDirectory()
    monkeypatch.setattr(directory, "open_session", lambda cfg: FakeSession(fake, cfg))
    return fake


@pytest.fixture()
def domain(client, ad):
    response = client.put("/api/directory", json=SETTINGS)
    assert response.status_code == 200, response.text
    return ad


def login(client, username, password):
    return client.post("/api/auth/login", json={"username": username, "password": password})


def users(client):
    return {u["username"]: u for u in client.get("/api/users").json()["items"]}


# ---------------------------------------------------------------- impostazioni
def test_impostazioni(client, anonymous, ad):
    current = client.get("/api/directory").json()
    assert current["enabled"] is False and current["security"] == "ldaps" and current["local_admins"] == 1
    assert anonymous.get("/api/auth/status").json()["directory"] is False

    def save(**changes):
        return client.put("/api/directory", json={**SETTINGS, **changes})

    assert save(servers=" ").json()["detail"] == "Indica almeno un domain controller"
    assert save(domain="").json()["detail"] == "Indica il dominio (per esempio azienda.local)"
    no_groups = save(admin_group="", editor_group=None, viewer_group=" ")
    assert no_groups.status_code == 422 and "almeno un gruppo" in no_groups.json()["detail"]
    assert save(ca_cert="non è un certificato").json()["detail"].startswith("Il certificato della CA non è valido")
    assert save(security="kerberos").status_code == 422
    # Spento si salva anche incompleto
    assert client.put("/api/directory", json={"enabled": False, "domain": "prova.lan"}).status_code == 200

    saved = save(base_dn=" ", default_role="viewer")
    assert saved.status_code == 200, saved.text
    assert saved.json()["base_dn"] is None and saved.json()["default_role"] == "viewer"
    assert anonymous.get("/api/auth/status").json()["directory"] is True
    history = client.get("/api/audit-log", params={"object_type": "directory"}).json()["items"]
    assert history[0]["label"] == "Active Directory"

    # Solo gli amministratori
    create(client, "/users", {"username": "tecnico", "password": "tecnico-123", "role": "editor"})
    login(anonymous, "tecnico", "tecnico-123")
    assert anonymous.get("/api/directory").status_code == 403
    assert anonymous.put("/api/directory", json=SETTINGS).status_code == 403


def test_base_di_ricerca_e_nomi():
    cfg = DirectorySettings(domain="prova.lan.", base_dn=None)
    assert directory.base_dn(cfg) == "DC=prova,DC=lan"
    cfg.base_dn = "OU=Sede,DC=prova,DC=lan"
    assert directory.base_dn(cfg) == "OU=Sede,DC=prova,DC=lan"
    assert directory.login_names(cfg, " mario ") == ("mario@prova.lan", "(&(objectCategory=person)(objectClass=user)(sAMAccountName=mario))")
    assert directory.login_names(cfg, "PROVA\\mario")[0] == "PROVA\\mario"
    assert "(userPrincipalName=m.rossi@azienda.it)" in directory.login_names(cfg, "m.rossi@azienda.it")[1]
    assert "(sAMAccountName=a\\2ab\\29)" in directory.login_names(cfg, "a*b)")[1]  # niente filtri iniettati
    assert directory.server_list("dc1, dc2;dc3  dc4") == ["dc1", "dc2", "dc3", "dc4"]


def test_codici_di_errore_del_bind():
    session = object.__new__(directory.LdapSession)
    session.where = "dc1"

    def result(code, message=""):
        session.conn = SimpleNamespace(bind=lambda: False, result={"result": code, "message": message, "description": "x"})
        return session.bind("mario@prova.lan", "x")

    assert result(49, "80090308: LdapErr: DSID-0C09044E, comment: AcceptSecurityContext error, data 52e, v4563") is False
    with pytest.raises(directory.LoginDenied, match="disattivato"):
        result(49, "80090308: LdapErr: DSID-0C09044E, comment: AcceptSecurityContext error, data 533, v4563")
    with pytest.raises(directory.LoginDenied, match="scaduta"):
        result(49, "... data 532, v4563")
    with pytest.raises(directory.DirectoryError, match="solo connessioni cifrate"):
        result(8, "BindSimple: Transport encryption required.")


# ---------------------------------------------------------------- accesso
def test_accesso_con_utente_di_dominio(client, anonymous, domain):
    me = login(anonymous, "Mario.Rossi", "Mario-2026")
    assert me.status_code == 200, me.text
    assert me.json()["user"] | {"id": 0, "created_at": None, "updated_at": None, "last_login_at": None} == {
        "id": 0, "username": "mario.rossi", "full_name": "Mario Rossi", "role": "admin", "active": True, "source": "ad",
        "created_at": None, "updated_at": None, "last_login_at": None,
    }
    assert domain.binds[-1] == "Mario.Rossi@prova.lan"
    assert anonymous.get("/api/users").status_code == 200  # è amministratore

    # Gruppo annidato (Tecnici dentro NetMap-Editor), nome scritto come DOMINIO\utente
    luca = login(anonymous, "PROVA\\luca.bianchi", "Luca-2026")
    assert luca.status_code == 200 and luca.json()["user"]["role"] == "editor"
    assert domain.binds[-1] == "PROVA\\luca.bianchi"

    # Sbagliate, vuote, utente disattivato in AD, utente in nessun gruppo
    assert login(anonymous, "luca.bianchi", "sbagliata").status_code == 401
    assert login(anonymous, "luca.bianchi", "").status_code == 401
    disabled = login(anonymous, "ex.dipendente", "Ex-2026")
    assert disabled.status_code == 403 and disabled.json()["detail"] == "Utente di dominio disattivato"
    nobody = login(anonymous, "anna.verdi", "Anna-2026")
    assert nobody.status_code == 403 and "nessun gruppo di NetMap" in nobody.json()["detail"]
    assert set(users(client)) == {"admin", "mario.rossi", "luca.bianchi"}

    # Con un ruolo predefinito entra anche chi non è nei gruppi
    client.put("/api/directory", json={**SETTINGS, "default_role": "viewer"})
    assert login(anonymous, "anna.verdi", "Anna-2026").json()["user"]["role"] == "viewer"

    # Lo storico dice che gli utenti li ha creati l'accesso di dominio
    created = client.get("/api/audit-log", params={"object_type": "user", "source": "directory"}).json()["items"]
    assert {e["label"] for e in created if e["action"] == "create"} == {"mario.rossi", "luca.bianchi", "anna.verdi"}


def test_ruolo_aggiornato_a_ogni_accesso(client, anonymous, domain):
    assert login(anonymous, "mario.rossi", "Mario-2026").json()["user"]["role"] == "admin"
    domain.users["mario.rossi"]["groups"] = {"NetMap-Viewer"}
    assert login(anonymous, "mario.rossi", "Mario-2026").json()["user"]["role"] == "viewer"
    assert anonymous.get("/api/sites").status_code == 200

    # Tolto da tutti i gruppi: non entra e la sessione aperta si chiude
    domain.users["mario.rossi"]["groups"] = set()
    with_session = anonymous.cookies.get("netmap_session")
    assert login(anonymous, "mario.rossi", "Mario-2026").status_code == 403
    assert anonymous.get("/api/sites", headers={"Authorization": f"Bearer {with_session}"}).status_code == 401
    assert users(client)["mario.rossi"]["role"] == "viewer"


def test_utente_di_dominio_non_modificabile_in_netmap(client, anonymous, domain):
    login(anonymous, "luca.bianchi", "Luca-2026")
    luca = users(client)["luca.bianchi"]
    url = f"/api/users/{luca['id']}"
    assert client.patch(url, json={"role": "admin"}).json()["detail"] == "Il ruolo degli utenti di dominio viene dai gruppi di Active Directory"
    assert client.patch(url, json={"password": "nuova-pass-1"}).status_code == 422
    assert client.patch(url, json={"username": "luca"}).status_code == 422
    assert client.patch(url, json={"role": "editor", "full_name": "Luca B.", "active": True}).status_code == 200
    # Cambio password dal menu: si fa in Windows
    changed = anonymous.post("/api/auth/password", json={"current_password": "Luca-2026", "new_password": "nuova-pass-1"})
    assert changed.status_code == 422 and "Windows" in changed.json()["detail"]

    # Disattivato in NetMap: non entra anche con la password giusta del dominio
    assert client.patch(url, json={"active": False}).status_code == 200
    assert login(anonymous, "luca.bianchi", "Luca-2026").status_code == 403
    # Eliminato: si ricrea al prossimo accesso
    assert client.patch(url, json={"active": True}).status_code == 200
    assert client.delete(url).status_code == 204
    assert login(anonymous, "luca.bianchi", "Luca-2026").status_code == 200


def test_utente_locale_e_omonimo_di_dominio(client, anonymous, domain):
    create(client, "/users", {"username": "luca.bianchi", "password": "locale-123", "role": "viewer"})
    # Il nome di un utente locale vale solo con la sua password, mai con quella del dominio
    assert login(anonymous, "luca.bianchi", "locale-123").json()["user"]["source"] == "local"
    assert login(anonymous, "luca.bianchi", "Luca-2026").status_code == 401
    clash = login(anonymous, "PROVA\\luca.bianchi", "Luca-2026")
    assert clash.status_code == 409 and "utente locale luca.bianchi" in clash.json()["detail"]
    # L'amministratore locale entra sempre, anche se il dominio non risponde
    domain.down = True
    assert login(anonymous, "admin", "password-di-prova").status_code == 200


def test_dominio_che_non_risponde(client, anonymous, domain):
    domain.down = True
    for _ in range(7):  # non conta come password sbagliata: niente blocco
        down = login(anonymous, "mario.rossi", "Mario-2026")
        assert down.status_code == 503 and "Nessun domain controller risponde" in down.json()["detail"]
    domain.down = False
    assert login(anonymous, "mario.rossi", "Mario-2026").status_code == 200

    # Accesso di dominio spento: gli utenti di dominio non entrano più
    client.put("/api/directory", json={**SETTINGS, "enabled": False})
    assert login(anonymous, "mario.rossi", "Mario-2026").status_code == 401
    assert users(client)["mario.rossi"]["source"] == "ad"


def test_prova_delle_impostazioni(client, ad):
    payload = {"settings": {**SETTINGS, "enabled": False, "viewer_group": "Gruppo-che-non-esiste"},
               "username": "luca.bianchi", "password": "Luca-2026"}
    result = client.post("/api/directory/test", json=payload).json()
    assert result["ok"] is True and result["role"] == "editor" and result["by_default"] is False
    assert result["user"]["dn"] == f"CN=Luca Bianchi,OU=Sede,{BASE}"
    assert [(g["role"], g["found"], g["member"]) for g in result["groups"]] == [
        ("admin", True, False), ("editor", True, True), ("viewer", False, False)]
    assert client.get("/api/directory").json()["enabled"] is False  # la prova non salva niente

    assert client.post("/api/directory/test", json={**payload, "password": "x"}).json() == {
        "ok": False, "message": "Nome utente o password sbagliati"}
    ad.down = True
    assert "Nessun domain controller" in client.post("/api/directory/test", json=payload).json()["message"]
    assert client.post("/api/directory/test", json={**payload, "settings": {**SETTINGS, "servers": ""}}).status_code == 422
