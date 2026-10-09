from datetime import datetime
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

from app.models.enums import DirectorySecurity, UserRole
from app.schemas.common import InputSchema, ReadSchema, make_partial


def _username(value: str) -> str:
    value = value.strip().lower()
    if not value:
        raise ValueError("Il nome utente non può essere vuoto")
    if any(c.isspace() for c in value):
        raise ValueError("Il nome utente non può contenere spazi")
    return value


Username = Annotated[str, Field(max_length=100), AfterValidator(_username)]
Password = Annotated[str, Field(min_length=8, max_length=200, description="Almeno 8 caratteri")]


class UserBase(InputSchema):
    username: Username
    first_name: str | None = Field(None, max_length=100)
    last_name: str | None = Field(None, max_length=100)
    role: UserRole = UserRole.VIEWER
    active: bool = True
    password: Password | None = Field(None, description="Solo scrittura: in modifica, vuota = invariata")


class UserCreate(UserBase):
    password: Password


UserUpdate = make_partial(UserBase, "UserUpdate")


class UserRead(ReadSchema):
    username: str
    first_name: str | None = None
    last_name: str | None = None
    full_name: str | None = None
    role: str
    active: bool
    source: str = "local"
    last_login_at: datetime | None = None


class LoginRequest(BaseModel):
    username: str = Field(..., max_length=100)
    password: str = Field(..., max_length=200)


class SetupRequest(InputSchema):
    username: Username
    first_name: str | None = Field(None, max_length=100)
    last_name: str | None = Field(None, max_length=100)
    password: Password


class PasswordChange(InputSchema):
    current_password: str = Field(..., max_length=200)
    new_password: Password


class AuthStatus(BaseModel):
    auth_enabled: bool
    setup_required: bool
    directory: bool = Field(False, description="Si può accedere con l'utente di Active Directory")


class LoginResult(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user: UserRead
    token: str = Field(..., description="Anche come cookie: serve solo a script e integrazioni (Authorization: Bearer)")


# ---------------------------------------------------------------- Active Directory
def _optional(max_length: int, description: str | None = None):
    """Testo facoltativo: vuoto o solo spazi = None."""
    return Annotated[str | None, Field(max_length=max_length, description=description),
                     AfterValidator(lambda v: (v.strip() or None) if v else None)]


class DirectorySettingsWrite(InputSchema):
    enabled: bool = False
    servers: str = Field("", max_length=500, description="Domain controller (nomi DNS) separati da virgola: vale il primo che risponde")
    security: DirectorySecurity = DirectorySecurity.LDAPS
    port: int | None = Field(None, ge=1, le=65535, description="Vuota = 636 con LDAPS, 389 con StartTLS o in chiaro")
    verify_cert: bool = True
    ca_cert: _optional(50000, "Certificato della CA del dominio (PEM)") = None
    domain: str = Field("", max_length=255, description="Dominio DNS, per esempio azienda.local")
    base_dn: _optional(500, "Vuota = tutto il dominio") = None
    admin_group: _optional(500, "Gruppo (nome o DN) dei membri con ruolo amministratore") = None
    editor_group: _optional(500, "Gruppo dei membri che modificano i dati") = None
    viewer_group: _optional(500, "Gruppo dei membri che consultano") = None
    default_role: UserRole | None = Field(None, description="Ruolo di chi non è in nessuno dei gruppi (vuoto = non entra)")


class DirectorySettingsRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    enabled: bool
    servers: str
    security: str
    port: int | None = None
    verify_cert: bool
    ca_cert: str | None = None
    domain: str
    base_dn: str | None = None
    admin_group: str | None = None
    editor_group: str | None = None
    viewer_group: str | None = None
    default_role: str | None = None
    updated_at: datetime | None = None
    local_admins: int = Field(0, description="Amministratori locali attivi: servono se il dominio non risponde")
    domain_users: int = 0


class DirectoryTest(BaseModel):
    settings: DirectorySettingsWrite
    username: str = Field(..., max_length=200)
    password: str = Field(..., max_length=200)
