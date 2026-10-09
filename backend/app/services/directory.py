"""Accesso con Active Directory: bind LDAP con le credenziali dell'utente, ruolo dai gruppi (anche annidati).

Niente account di servizio: l'utente si collega come utente@dominio (o DOMINIO\\utente, o con il suo UPN) e con la
stessa connessione si leggono i suoi dati e i gruppi (in AD ogni utente autenticato può leggere la directory).
I gruppi annidati valgono grazie alla regola LDAP_MATCHING_RULE_IN_CHAIN, che conoscono AD e Samba.
Le operazioni LDAP stanno in `LdapSession`: nei test la si sostituisce con una directory finta (`open_session`).
"""
import logging
import re
import ssl
from dataclasses import dataclass, field

from ldap3 import BASE, FIRST, NONE, SIMPLE, SUBTREE, Connection, Server, ServerPool, Tls
from ldap3.core.exceptions import LDAPException, LDAPServerPoolExhaustedError, LDAPSocketOpenError, LDAPStartTLSError
from ldap3.utils.conv import escape_filter_chars

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import DirectorySettings
from app.models.enums import DirectorySecurity, UserRole

log = logging.getLogger("netmap.auth")

TIMEOUT = 10
IN_CHAIN = "1.2.840.113556.1.4.1941"
USER_ATTRIBUTES = ["sAMAccountName", "givenName", "sn", "displayName", "mail", "userPrincipalName"]
ROLE_GROUPS = (
    (UserRole.ADMIN.value, "admin_group"), (UserRole.EDITOR.value, "editor_group"), (UserRole.VIEWER.value, "viewer_group"),
)
# Codice "data" dei bind rifiutati da AD (dopo la password giusta): cosa dire all'utente
BIND_REASONS = {
    "532": "La password di dominio è scaduta: cambiala da un PC Windows e riprova",
    "773": "La password di dominio va cambiata: cambiala da un PC Windows e riprova",
    "533": "Utente di dominio disattivato",
    "701": "Utente di dominio scaduto",
    "775": "Utente di dominio bloccato per troppi tentativi: riprova più tardi o chiedi all'amministratore del dominio",
}


class DirectoryError(Exception):
    """Domain controller che non risponde, certificato, configurazione: il messaggio è per l'utente."""


class LoginDenied(Exception):
    """Credenziali giuste ma accesso negato da AD (password scaduta, utente disattivato...)."""


@dataclass
class GroupCheck:
    role: str
    group: str
    dn: str | None = None  # None = gruppo non trovato
    member: bool = False


@dataclass
class DirectoryUser:
    username: str  # sAMAccountName in minuscolo: il nome utente in NetMap
    dn: str
    first_name: str | None
    last_name: str | None
    email: str | None
    role: str | None  # None = in nessun gruppo di NetMap (e nessun ruolo predefinito)
    groups: list[GroupCheck] = field(default_factory=list)


def settings_row(db: Session) -> DirectorySettings:
    """La riga delle impostazioni (la crea, spenta, la prima volta)."""
    row = db.scalars(select(DirectorySettings).order_by(DirectorySettings.id)).first()
    if row is None:
        row = DirectorySettings(enabled=False, servers="", domain="")
        db.add(row)
        db.flush()
    return row


def active_settings(db: Session) -> DirectorySettings | None:
    row = db.scalars(select(DirectorySettings).order_by(DirectorySettings.id)).first()
    return row if row is not None and row.enabled else None


def server_list(text: str | None) -> list[str]:
    return [s for s in re.split(r"[\s,;]+", text or "") if s]


def _domain(cfg: DirectorySettings) -> str:
    return (cfg.domain or "").strip().strip(".")


def domain_dn(cfg: DirectorySettings) -> str:
    return ",".join(f"DC={part}" for part in _domain(cfg).split(".") if part)


def base_dn(cfg: DirectorySettings) -> str:
    """Dove si cercano gli utenti; i gruppi si cercano sempre in tutto il dominio."""
    if cfg.base_dn and cfg.base_dn.strip():
        return cfg.base_dn.strip()
    return domain_dn(cfg)


def login_names(cfg: DirectorySettings, login: str) -> tuple[str, str]:
    """Nome per il bind e filtro di ricerca dell'utente, da come l'ha scritto: mario, AZIENDA\\mario, mario@azienda.it."""
    login = login.strip()
    person = "(objectCategory=person)(objectClass=user)"
    if "\\" in login:
        sam = login.split("\\", 1)[1]
        return login, f"(&{person}(sAMAccountName={escape_filter_chars(sam)}))"
    if "@" in login:
        return login, f"(&{person}(|(userPrincipalName={escape_filter_chars(login)})(sAMAccountName={escape_filter_chars(login.split('@', 1)[0])})))"
    return f"{login}@{_domain(cfg)}", f"(&{person}(sAMAccountName={escape_filter_chars(login)}))"


class LdapSession:
    """Connessione LDAP aperta (non ancora autenticata) verso il primo domain controller che risponde."""

    def __init__(self, cfg: DirectorySettings):
        self.cfg = cfg
        hosts = server_list(cfg.servers)
        if not hosts:
            raise DirectoryError("Manca il nome del domain controller")
        security = cfg.security or DirectorySecurity.LDAPS.value
        use_ssl = security == DirectorySecurity.LDAPS.value
        port = cfg.port or (636 if use_ssl else 389)
        tls = None
        if security != DirectorySecurity.NONE.value:
            tls = Tls(validate=ssl.CERT_REQUIRED if cfg.verify_cert else ssl.CERT_NONE,
                      ca_certs_data=(cfg.ca_cert or "").strip() or None)
        servers = [Server(h, port=port, use_ssl=use_ssl, tls=tls, connect_timeout=TIMEOUT, get_info=NONE) for h in hosts]
        pool = ServerPool(servers, FIRST, active=1, exhaust=False)
        self.where = ", ".join(hosts)
        self.conn = Connection(pool, authentication=SIMPLE, receive_timeout=TIMEOUT, raise_exceptions=False,
                               auto_referrals=False)
        try:
            self.conn.open()
            if security == DirectorySecurity.STARTTLS.value:
                if not self.conn.start_tls():
                    raise DirectoryError(f"StartTLS rifiutato da {self.where}: {self.conn.result.get('description')}")
        except DirectoryError:
            raise
        except LDAPException as exc:
            raise DirectoryError(self._message(exc)) from exc

    def _message(self, exc: Exception) -> str:
        text = str(exc)
        if "doesn't match" in text:
            return ("Il certificato del domain controller è intestato a un altro nome: scrivi il server con il nome che "
                    "c'è nel certificato (di solito il nome completo, per esempio dc1.azienda.local)")
        if "CERTIFICATE_VERIFY_FAILED" in text:
            return ("Il certificato del domain controller non è firmato da una CA conosciuta: incolla il certificato "
                    "della CA del dominio, oppure disattiva la verifica")
        if "WRONG_VERSION_NUMBER" in text or "Connection reset" in text:
            return (f"{self.where} ha chiuso la connessione cifrata: controlla porta e sicurezza "
                    "(LDAPS sulla 636, StartTLS sulla 389) e che il domain controller abbia un certificato")
        if isinstance(exc, (LDAPSocketOpenError, LDAPServerPoolExhaustedError)) or "timed out" in text:
            return f"Nessun domain controller risponde ({self.where}): controlla nome, porta e firewall"
        if isinstance(exc, LDAPStartTLSError):
            return f"StartTLS non riuscito con {self.where}: il domain controller ha un certificato?"
        return f"Errore LDAP con {self.where}: {text}"

    def bind(self, name: str, password: str) -> bool:
        """True se le credenziali sono giuste; False se sbagliate; LoginDenied/DirectoryError negli altri casi."""
        self.conn.user, self.conn.password = name, password
        try:
            if self.conn.bind():
                return True
        except LDAPException as exc:
            raise DirectoryError(self._message(exc)) from exc
        result = self.conn.result or {}
        if result.get("result") == 49:  # invalidCredentials; il codice "data" dice perché
            code = re.search(r"data ([0-9a-f]+)", result.get("message") or "")
            if code and code.group(1) in BIND_REASONS:
                raise LoginDenied(BIND_REASONS[code.group(1)])
            return False
        if result.get("result") == 8:  # strongerAuthRequired
            raise DirectoryError("Il domain controller accetta solo connessioni cifrate: scegli LDAPS o StartTLS")
        raise DirectoryError(f"Accesso LDAP rifiutato: {result.get('description')} {result.get('message') or ''}".strip())

    def search(self, base: str, filter_: str, scope=SUBTREE, attributes=None) -> list:
        try:
            self.conn.search(base, filter_, scope, attributes=attributes or [], size_limit=2)
        except LDAPException as exc:
            raise DirectoryError(self._message(exc)) from exc
        if self.conn.result.get("result") not in (0, 4):  # 4 = sizeLimitExceeded
            if self.conn.result.get("result") == 32:  # noSuchObject
                raise DirectoryError(f"La base di ricerca {base} non esiste nel dominio")
            raise DirectoryError(f"Ricerca LDAP non riuscita: {self.conn.result.get('description')}")
        return [e for e in self.conn.entries if e.entry_dn]

    def find_user(self, filter_: str):
        found = self.search(base_dn(self.cfg), filter_, attributes=USER_ATTRIBUTES)
        return found[0] if len(found) == 1 else None

    def group_dn(self, group: str) -> str | None:
        """Gruppo scritto come DN oppure come nome (cn o nome pre-Windows 2000)."""
        if "=" in group:
            return group
        name = escape_filter_chars(group)
        found = self.search(domain_dn(self.cfg), f"(&(objectClass=group)(|(cn={name})(sAMAccountName={name})))")
        return found[0].entry_dn if found else None

    def is_member(self, user_dn: str, group_dn: str) -> bool:
        return bool(self.search(user_dn, f"(memberOf:{IN_CHAIN}:={escape_filter_chars(group_dn)})", BASE))

    def close(self) -> None:
        try:
            self.conn.unbind()
        except Exception:  # noqa: BLE001 - chiusura di una connessione già caduta
            pass


def open_session(cfg: DirectorySettings) -> LdapSession:
    return LdapSession(cfg)


def _value(entry, name: str) -> str | None:
    try:
        value = entry[name].value
    except (KeyError, IndexError, AttributeError):
        return None
    if isinstance(value, list):
        value = value[0] if value else None
    return str(value) if value else None


def authenticate(cfg: DirectorySettings, login: str, password: str, *, check_all: bool = False) -> DirectoryUser | None:
    """Utente di dominio con il suo ruolo, None se nome o password sono sbagliati.

    check_all: controlla tutti i gruppi (per la prova nella pagina), non solo fino al primo che dà un ruolo.
    """
    if not password or not login.strip():
        return None  # un bind con la password vuota in LDAP "riesce" come anonimo: mai
    bind_name, user_filter = login_names(cfg, login)
    session = open_session(cfg)
    try:
        if not session.bind(bind_name, password):
            return None
        entry = session.find_user(user_filter)
        if entry is None:
            # Password giusta ma utente fuori dalla base di ricerca: la base serve anche a limitare chi entra
            raise LoginDenied(f"Il tuo utente di dominio non è sotto {base_dn(cfg)}, dove NetMap cerca gli utenti: "
                              "chiedi a un amministratore")
        user = DirectoryUser(
            username=(_value(entry, "sAMAccountName") or login).lower(), dn=entry.entry_dn,
            first_name=_value(entry, "givenName"), last_name=_value(entry, "sn"), email=_value(entry, "mail"), role=None,
        )
        if not (user.first_name or user.last_name):  # utenti senza nome e cognome: il nome visualizzato
            user.first_name, _, rest = (_value(entry, "displayName") or "").partition(" ")
            user.first_name, user.last_name = user.first_name or None, rest.strip() or None
        for role, column in ROLE_GROUPS:
            group = (getattr(cfg, column) or "").strip()
            if not group:
                continue
            check = GroupCheck(role=role, group=group, dn=session.group_dn(group))
            if check.dn is None:
                log.warning("Gruppo di Active Directory %r non trovato (ruolo %s)", group, role)
            else:
                check.member = session.is_member(user.dn, check.dn)
            user.groups.append(check)
            if check.member and user.role is None:
                user.role = role
                if not check_all:
                    break
        if user.role is None and cfg.default_role:
            user.role = cfg.default_role
        return user
    finally:
        session.close()
