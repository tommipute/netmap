"""Regole di coerenza dei dati, eseguite prima del salvataggio (hook dei router CRUD)."""
import ipaddress
from typing import Any

from fastapi import HTTPException
from sqlalchemy import func, inspect, or_, select
from sqlalchemy.orm import Session

from app.core.auth import hash_password
from app.core.net import normalize_ip_interface
from app.core.secrets import SecretError, encrypt
from app.models import (
    VLAN, Cable, Device, DeviceType, Interface, IPAddress, Location, Prefix, Rack, SnmpProfile, StackMember, User,
)
from app.models.enums import NON_CABLEABLE_TYPES, InterfaceMode, InterfaceType, SnmpVersion, UserRole


def _fail(message: str) -> None:
    raise HTTPException(422, message)


def _same(column, value):
    """Confronto che tratta NULL come un valore (es. VRF globale)."""
    return column.is_(None) if value is None else column == value


def location_hook(db: Session, loc: Location, data: dict[str, Any], is_create: bool) -> None:
    # Il vincolo unico (sede, padre, nome) non vale al livello principale: Postgres considera diversi i NULL
    twin = db.scalar(select(Location.id).where(
        Location.site_id == loc.site_id, _same(Location.parent_id, loc.parent_id), Location.name == loc.name,
        Location.id != (loc.id or 0),
    ))
    if twin is not None:
        _fail(f"Esiste già una posizione {loc.name} a questo livello della sede")
    if loc.parent_id is None:
        return
    parent = db.get(Location, loc.parent_id)
    if parent.site_id != loc.site_id:
        _fail("La posizione padre appartiene a un'altra sede")
    # Evita gerarchie circolari (A dentro B dentro A)
    current, seen = parent, set()
    while current is not None and current.id not in seen:
        if loc.id is not None and current.id == loc.id:
            _fail("Gerarchia circolare: una posizione non può stare dentro se stessa")
        seen.add(current.id)
        current = db.get(Location, current.parent_id) if current.parent_id else None


def rack_hook(db: Session, rack: Rack, data: dict[str, Any], is_create: bool) -> None:
    if rack.location_id is not None and db.get(Location, rack.location_id).site_id != rack.site_id:
        _fail("La posizione appartiene a un'altra sede")
    # Rack spostato in un'altra posizione: i suoi device lo seguono (uno per uno, così finiscono nello storico)
    if not is_create and rack.location_id is not None and inspect(rack).attrs.location_id.history.has_changes():
        for device in db.scalars(select(Device).where(Device.rack_id == rack.id, Device.location_id.is_distinct_from(rack.location_id))):
            device.location_id = rack.location_id


def device_hook(db: Session, device: Device, data: dict[str, Any], is_create: bool) -> None:
    # Un device nel rack sta dove sta il rack: prende la sua posizione (se il rack ne ha una)
    if device.rack_id is not None:
        rack = db.get(Rack, device.rack_id)
        if rack is not None and rack.location_id is not None and rack.site_id == device.site_id:
            device.location_id = rack.location_id
    if device.location_id is not None and db.get(Location, device.location_id).site_id != device.site_id:
        _fail("La posizione appartiene a un'altra sede")
    if device.rack_id is not None and db.get(Rack, device.rack_id).site_id != device.site_id:
        _fail("Il rack appartiene a un'altra sede")
    # Fuori dal rack (o in un altro rack): le unità dei membri di uno stack non valgono più
    if not is_create and inspect(device).attrs.rack_id.history.has_changes():
        for member in db.scalars(select(StackMember).where(StackMember.device_id == device.id)):
            member.rack_position = None
    # Senza ruolo: quello predefinito del modello (alla creazione o quando cambia il modello)
    type_changed = is_create or inspect(device).attrs.device_type_id.history.has_changes()
    if device.role_id is None and device.device_type_id and type_changed:
        device.role_id = db.scalar(select(DeviceType.default_role_id).where(DeviceType.id == device.device_type_id))
    # Campo "IP di management" del modulo: assente = invariato, vuoto = il device non ne ha più uno
    if "management_ip" in data:
        db.flush()  # un device nuovo deve avere l'id prima di creargli la porta
        set_management_ip(db, device, (data["management_ip"] or "").strip())


def device_type_hook(db: Session, device_type: DeviceType, data: dict[str, Any], is_create: bool) -> None:
    """Ruolo predefinito impostato o cambiato: lo prendono anche i device di questo modello ancora senza ruolo."""
    if is_create or device_type.default_role_id is None:
        return
    if inspect(device_type).attrs.default_role_id.history.has_changes():
        db.flush()
        for device in db.scalars(select(Device).where(Device.device_type_id == device_type.id, Device.role_id.is_(None))):
            device.role_id = device_type.default_role_id  # uno per uno: così finiscono nello storico


def device_delete_hook(db: Session, device: Device, params: dict) -> None:
    """DELETE /api/devices/{id}?with_ips=true: elimina anche gli IP delle sue porte. Senza, restano registrati
    come liberi (utile se l'indirizzo è ancora documentato in IPAM)."""
    if str(params.get("with_ips", "")).lower() not in ("1", "true", "yes", "si", "sì"):
        return
    ips = db.scalars(select(IPAddress).join(Interface, IPAddress.interface_id == Interface.id).where(Interface.device_id == device.id))
    for ip in ips:
        db.delete(ip)


# ---------------------------------------------------------------- IP di management (uno per device)
MGMT_NAMES = ["mgmt", "management", "eth0"]


def _management_ips(db: Session, device_id: int):
    return (
        select(IPAddress)
        .join(Interface, IPAddress.interface_id == Interface.id)
        .where(Interface.device_id == device_id, IPAddress.is_primary.is_(True))
    )


def set_management_ip(db: Session, device: Device, value: str) -> None:
    """Imposta l'IP di management di un device (modulo del device e import CSV).

    L'IP resta sulla sua porta se è già del device; altrimenti va sulla porta dell'IP di management attuale,
    poi su una porta di management (mgmt_only o di nome mgmt/management/eth0), altrimenti se ne crea una "mgmt".
    Valore vuoto: l'IP attuale resta sulla sua porta ma non è più quello di management.
    """
    current = db.scalars(_management_ips(db, device.id)).first()
    if not value:
        if current is not None:
            current.is_primary = False
        return
    try:
        address = normalize_ip_interface(value)
    except ValueError as exc:
        _fail(str(exc))
    host = str(ipaddress.ip_interface(address).ip)
    if current is not None and current.host == host:
        current.address = address  # stesso IP (al massimo cambia la maschera): resta dov'è, VRF compresa
        db.flush()
        return

    # Il modulo del device non ha la VRF: l'IP di management sta nella tabella globale
    ip_obj = db.scalars(select(IPAddress).where(IPAddress.host == host, IPAddress.vrf_id.is_(None))).first()
    if ip_obj is not None and ip_obj.interface is not None and ip_obj.interface.device_id != device.id:
        _fail(f"L'IP {host} è già assegnato a {ip_obj.interface.device.name} {ip_obj.interface.name}")

    if ip_obj is not None and ip_obj.interface is not None:
        iface = ip_obj.interface  # già su questo device: resta sulla sua porta
    else:
        iface = (current.interface if current is not None else None) or db.scalars(
            select(Interface)
            .where(
                Interface.device_id == device.id,
                or_(Interface.mgmt_only.is_(True), func.lower(Interface.name).in_(MGMT_NAMES)),
            )
            .order_by(Interface.mgmt_only.desc(), Interface.id)
        ).first()
        if iface is None:
            iface = Interface(
                device_id=device.id,
                name="mgmt",
                type=InterfaceType.COPPER.value,
                mgmt_only=True,
                description="Porta di management creata da NetMap",
            )
            db.add(iface)
            db.flush()

    if current is not None and current is not ip_obj:
        current.is_primary = False  # l'IP di management è uno solo: il vecchio resta, senza il flag
    if ip_obj is None:
        ip_obj = IPAddress(address=address, interface_id=iface.id, is_primary=True)
        db.add(ip_obj)
    else:
        ip_obj.address = address
        ip_obj.interface_id = iface.id
        ip_obj.is_primary = True
    db.flush()
    ip_hook(db, ip_obj, {}, False)


def interface_hook(db: Session, iface: Interface, data: dict[str, Any], is_create: bool) -> None:
    # VLAN tagged solo sui trunk
    if iface.mode != InterfaceMode.TRUNK.value:
        if data.get("tagged_vlan_ids"):
            _fail("Le VLAN tagged si possono assegnare solo a interfacce in modalità trunk")
        iface.tagged_vlans = []
    elif "tagged_vlan_ids" in data:
        ids = data["tagged_vlan_ids"] or []
        vlans = list(db.scalars(select(VLAN).where(VLAN.id.in_(ids)))) if ids else []
        missing = set(ids) - {v.id for v in vlans}
        if missing:
            _fail(f"VLAN non trovate: {sorted(missing)}")
        iface.tagged_vlans = vlans

    # Appartenenza a un LAG
    if iface.lag_id is not None:
        lag = db.get(Interface, iface.lag_id)
        if iface.id is not None and lag.id == iface.id:
            _fail("Un'interfaccia non può essere membro di se stessa")
        if lag.device_id != iface.device_id or lag.type != InterfaceType.LAG.value:
            _fail("lag_id deve essere un'interfaccia di tipo 'lag' dello stesso device")

    # Non si può rendere virtuale un'interfaccia che ha un cavo
    if not is_create and iface.type in NON_CABLEABLE_TYPES:
        cabled = db.scalar(
            select(Cable.id).where(or_(Cable.a_interface_id == iface.id, Cable.b_interface_id == iface.id))
        )
        if cabled:
            _fail("L'interfaccia ha un cavo collegato: non può diventare virtuale o LAG")


def cable_hook(db: Session, cable: Cable, data: dict[str, Any], is_create: bool) -> None:
    a_id, b_id = cable.a_interface_id, cable.b_interface_id
    if a_id == b_id:
        _fail("Le due estremità del cavo devono essere interfacce diverse")
    for iface_id in (a_id, b_id):
        iface = db.get(Interface, iface_id)
        if iface.type in NON_CABLEABLE_TYPES:
            _fail(f"L'interfaccia '{iface.name}' è di tipo '{iface.type}' e non può avere un cavo")
    stmt = select(Cable.id).where(
        or_(Cable.a_interface_id.in_([a_id, b_id]), Cable.b_interface_id.in_([a_id, b_id]))
    )
    if cable.id is not None:
        stmt = stmt.where(Cable.id != cable.id)
    if db.scalar(stmt):
        _fail("Una delle due interfacce ha già un cavo collegato")


def vlan_hook(db: Session, vlan: VLAN, data: dict[str, Any], is_create: bool) -> None:
    stmt = select(VLAN.id).where(VLAN.vid == vlan.vid, _same(VLAN.site_id, vlan.site_id))
    if vlan.id is not None:
        stmt = stmt.where(VLAN.id != vlan.id)
    if db.scalar(stmt):
        _fail(f"La VLAN {vlan.vid} esiste già per questa sede")


def prefix_hook(db: Session, prefix: Prefix, data: dict[str, Any], is_create: bool) -> None:
    stmt = select(Prefix.id).where(Prefix.prefix == prefix.prefix, _same(Prefix.vrf_id, prefix.vrf_id))
    if prefix.id is not None:
        stmt = stmt.where(Prefix.id != prefix.id)
    if db.scalar(stmt):
        _fail(f"Il prefisso {prefix.prefix} esiste già in questa VRF")


def ip_hook(db: Session, ip: IPAddress, data: dict[str, Any], is_create: bool) -> None:
    stmt = select(IPAddress.id).where(IPAddress.host == ip.host, _same(IPAddress.vrf_id, ip.vrf_id))
    if ip.id is not None:
        stmt = stmt.where(IPAddress.id != ip.id)
    if db.scalar(stmt):
        _fail(f"L'indirizzo {ip.host} esiste già in questa VRF")

    if ip.interface_id is None:
        ip.is_primary = False  # un IP non assegnato non può essere il primario di un device
    elif ip.is_primary:
        # Un solo IP di management per device: non lo si toglie di nascosto a un altro IP
        device_id = db.scalar(select(Interface.device_id).where(Interface.id == ip.interface_id))
        others = _management_ips(db, device_id)
        if ip.id is not None:
            others = others.where(IPAddress.id != ip.id)
        existing = db.scalars(others).first()
        if existing is not None:
            _fail(
                f"Il device ha già un IP di management ({existing.address}): ce n'è uno solo. "
                "Cambialo dalla scheda del device, oppure togli prima il flag all'IP attuale"
            )


def map_hook(db: Session, network_map, data: dict[str, Any], is_create: bool) -> None:
    if network_map.location_id is not None and db.get(Location, network_map.location_id).site_id != network_map.site_id:
        _fail("La posizione appartiene a un'altra sede")


# ---------- Avvisi ----------
_ALERT_SECRET = {"email": "smtp_password", "webhook": "webhook_url", "telegram": "telegram_token"}


def alert_channel_hook(db: Session, channel, data: dict[str, Any], is_create: bool) -> None:
    """Il segreto (password SMTP, indirizzo del webhook, token Telegram) si salva solo cifrato; per tipo, i dati minimi."""
    field = _ALERT_SECRET.get(channel.type)
    try:
        if field and field in data:
            channel.secret_enc = encrypt(data[field]) if data[field] else None
    except SecretError as exc:
        raise HTTPException(500, str(exc)) from exc
    if channel.type == "email":
        if not channel.email_to or not channel.smtp_host:
            _fail("Per l'email servono almeno un destinatario e il server SMTP")
        if any("@" not in address for address in channel.email_to):
            _fail("Un destinatario non sembra un indirizzo email")
    elif channel.type == "webhook":
        if not channel.secret_enc:
            _fail("Serve l'indirizzo del webhook")
        if field in data and data[field] and not str(data[field]).startswith(("https://", "http://")):
            _fail("L'indirizzo del webhook deve iniziare con https://")
    elif channel.type == "telegram" and (not channel.secret_enc or not channel.telegram_chat_id):
        _fail("Per Telegram servono il token del bot e la chat")


# ---------- Scansione SNMP ----------
_SECRETS = {"community": "community_enc", "auth_key": "auth_key_enc", "priv_key": "priv_key_enc"}


def snmp_profile_hook(db: Session, profile: SnmpProfile, data: dict[str, Any], is_create: bool) -> None:
    # I segreti arrivano in chiaro e si salvano solo cifrati. Campo assente = invariato, null o vuoto = cancellato
    try:
        for field, column in _SECRETS.items():
            if field in data:
                setattr(profile, column, encrypt(data[field]) if data[field] else None)
    except SecretError as exc:
        raise HTTPException(500, str(exc)) from exc

    if profile.version == SnmpVersion.V2C.value:
        if not profile.community_enc:
            _fail("Per SNMP v2c serve la community")
        return
    if not profile.username:
        _fail("Per SNMPv3 serve il nome utente")
    if profile.auth_protocol and not profile.auth_key_enc:
        _fail("Hai scelto un protocollo di autenticazione: serve anche la chiave")
    if profile.priv_protocol:
        if not profile.auth_protocol:
            _fail("La cifratura (privacy) in SNMPv3 richiede anche l'autenticazione")
        if not profile.priv_key_enc:
            _fail("Hai scelto un protocollo di cifratura: serve anche la chiave")


def discovery_job_hook(db: Session, job, data: dict[str, Any], is_create: bool) -> None:
    ids = list(dict.fromkeys(job.profile_ids or []))  # senza doppioni, ordine mantenuto
    if not ids:
        _fail("Scegli almeno un profilo SNMP")
    found = set(db.scalars(select(SnmpProfile.id).where(SnmpProfile.id.in_(ids))))
    missing = [i for i in ids if i not in found]
    if missing:
        _fail(f"Profili SNMP non trovati: {missing}")
    job.profile_ids = ids


# ---------- Utenti (fase 4) ----------
def _other_active_admins(db: Session, user: User) -> int:
    stmt = select(User.id).where(User.role == UserRole.ADMIN.value, User.active.is_(True))
    if user.id is not None:
        stmt = stmt.where(User.id != user.id)
    return len(db.scalars(stmt).all())


def user_hook(db: Session, user: User, data: dict[str, Any], is_create: bool) -> None:
    stmt = select(User.id).where(User.username == user.username)
    if user.id is not None:
        stmt = stmt.where(User.id != user.id)
    if db.scalar(stmt):
        _fail(f"Il nome utente {user.username} è già usato")
    if data.get("password"):
        user.password_hash = hash_password(data["password"])
        if not is_create:
            user.token_version = (user.token_version or 0) + 1  # le sessioni aperte di quell'utente scadono
    elif is_create:
        _fail("Serve una password")
    if not is_create:
        if ("active" in data and not user.active) or ("role" in data and user.role != UserRole.ADMIN.value):
            if _other_active_admins(db, user) == 0:
                _fail("Serve almeno un amministratore attivo: questo è l'ultimo")
        if "active" in data and not user.active:
            user.token_version = (user.token_version or 0) + 1


def user_delete_hook(db: Session, user: User, params: dict) -> None:
    if user.role == UserRole.ADMIN.value and user.active and _other_active_admins(db, user) == 0:
        raise HTTPException(409, "Non puoi eliminare l'ultimo amministratore attivo")


def stack_member_hook(db: Session, member: StackMember, data: dict[str, Any], is_create: bool) -> None:
    # Il numero è unico nello stack: messaggio chiaro invece del 409 generico
    same = select(StackMember.id).where(StackMember.device_id == member.device_id, StackMember.number == member.number)
    if member.id is not None:
        same = same.where(StackMember.id != member.id)
    with db.no_autoflush:
        clash = db.scalar(same)
    if clash:
        _fail(f"Lo stack ha già un membro numero {member.number}")
    if member.rack_position is not None:
        device = db.get(Device, member.device_id)
        if device.rack_id is None:
            _fail("Per indicare l'unità il device dello stack deve essere in un rack")
