from datetime import datetime
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

from app.models.enums import UserRole
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
    full_name: str | None = Field(None, max_length=200)
    role: UserRole = UserRole.VIEWER
    active: bool = True
    password: Password | None = Field(None, description="Solo scrittura: in modifica, vuota = invariata")


class UserCreate(UserBase):
    password: Password


UserUpdate = make_partial(UserBase, "UserUpdate")


class UserRead(ReadSchema):
    username: str
    full_name: str | None = None
    role: str
    active: bool
    last_login_at: datetime | None = None


class LoginRequest(BaseModel):
    username: str = Field(..., max_length=100)
    password: str = Field(..., max_length=200)


class SetupRequest(InputSchema):
    username: Username
    full_name: str | None = Field(None, max_length=200)
    password: Password


class PasswordChange(InputSchema):
    current_password: str = Field(..., max_length=200)
    new_password: Password


class AuthStatus(BaseModel):
    auth_enabled: bool
    setup_required: bool


class LoginResult(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user: UserRead
    token: str = Field(..., description="Anche come cookie: serve solo a script e integrazioni (Authorization: Bearer)")
