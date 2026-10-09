"""Valori ammessi per stati e tipi. Nel DB sono salvati come semplici stringhe,
così aggiungere un valore non richiede migration."""
from enum import StrEnum


class Source(StrEnum):
    MANUAL = "manual"
    SNMP = "snmp"


class DeviceStatus(StrEnum):
    ACTIVE = "active"
    PLANNED = "planned"
    OFFLINE = "offline"
    DECOMMISSIONED = "decommissioned"


class InterfaceType(StrEnum):
    COPPER = "copper"
    FIBER = "fiber"
    WIRELESS = "wireless"
    VIRTUAL = "virtual"   # SVI / VLAN interface / loopback
    LAG = "lag"           # port-channel / trunk aggregato
    OTHER = "other"


class InterfaceMode(StrEnum):
    ACCESS = "access"
    TRUNK = "trunk"


class CableType(StrEnum):
    CAT5E = "cat5e"
    CAT6 = "cat6"
    CAT6A = "cat6a"
    FIBER_SM = "fiber_sm"
    FIBER_MM = "fiber_mm"
    DAC = "dac"
    OTHER = "other"


class CableStatus(StrEnum):
    CONNECTED = "connected"
    PLANNED = "planned"
    DECOMMISSIONING = "decommissioning"


class IPAMStatus(StrEnum):
    ACTIVE = "active"
    RESERVED = "reserved"
    DEPRECATED = "deprecated"


class IPAddressStatus(StrEnum):
    ACTIVE = "active"
    RESERVED = "reserved"
    DHCP = "dhcp"
    DEPRECATED = "deprecated"


# Interfacce che non possono avere un cavo fisico
NON_CABLEABLE_TYPES = {InterfaceType.VIRTUAL.value, InterfaceType.LAG.value}


# ---------- Scansione SNMP (fase 3) ----------
class SnmpVersion(StrEnum):
    V1 = "v1"  # apparati vecchi: niente GETBULK né contatori a 64 bit
    V2C = "v2c"
    V3 = "v3"


class SnmpAuthProtocol(StrEnum):
    MD5 = "md5"
    SHA = "sha"
    SHA256 = "sha256"
    SHA512 = "sha512"


class SnmpPrivProtocol(StrEnum):
    DES = "des"
    AES = "aes"
    AES256 = "aes256"


class RunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


class ChangeStatus(StrEnum):
    PENDING = "pending"
    APPLIED = "applied"
    REJECTED = "rejected"
    FAILED = "failed"   # approvata ma non applicabile (es. porta nel frattempo occupata)


class ChangeAction(StrEnum):
    CREATE = "create"
    UPDATE = "update"
    STALE = "stale"     # non più vista dalla scansione: approvare = eliminare


class ChangeObject(StrEnum):
    DEVICE = "device"
    INTERFACE = "interface"
    IP = "ip"
    CABLE = "cable"
    VLAN = "vlan"
    STACK_MEMBER = "stack_member"


# ---------- Login (fase 4) ----------
class UserRole(StrEnum):
    ADMIN = "admin"     # tutto, compresi gli utenti
    EDITOR = "editor"   # modifica i dati
    VIEWER = "viewer"   # solo consultazione


class UserSource(StrEnum):
    LOCAL = "local"     # password in NetMap
    AD = "ad"           # utente di dominio (Active Directory)


class DirectorySecurity(StrEnum):
    LDAPS = "ldaps"         # porta 636, cifrata dall'inizio
    STARTTLS = "starttls"   # porta 389, poi cifrata
    NONE = "none"           # in chiaro: i domain controller recenti la rifiutano
