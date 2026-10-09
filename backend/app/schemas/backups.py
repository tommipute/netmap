from datetime import datetime
from enum import StrEnum

from pydantic import Field

from app.schemas.common import InputSchema, Name, ReadSchema, make_partial


class BackupTargetType(StrEnum):
    SMB = "smb"
    SFTP = "sftp"


class BackupTargetBase(InputSchema):
    name: Name
    enabled: bool = True
    host: str = Field(..., min_length=1, max_length=255, description="Nome o indirizzo del server")
    port: int | None = Field(None, ge=1, le=65535, description="Vuota = 445 (SMB) o 22 (SFTP)")
    share: str | None = Field(None, max_length=255, description="SMB: nome della condivisione")
    folder: str = Field("", max_length=500, description="Cartella dentro la condivisione o sul server (vuota = principale)")
    username: str = Field(..., min_length=1, max_length=255)
    keep_days: int = Field(30, ge=0, le=3650, description="Giorni dopo cui le copie si cancellano dalla destinazione (0 = mai)")
    include_key: bool = Field(False, description="Copia anche la chiave che cifra le password salvate")
    description: str | None = None
    # Solo scrittura (salvati cifrati): assenti = invariati, vuoti = cancellati
    password: str | None = Field(None, max_length=255)
    private_key: str | None = Field(None, max_length=20000)


class BackupTargetCreate(BackupTargetBase):
    type: BackupTargetType


class _BackupTargetEdit(BackupTargetBase):
    # SFTP: dimentica la chiave registrata del server (reinstallato o cambiato): alla prossima connessione si registra la nuova
    forget_host_key: bool = False


BackupTargetUpdate = make_partial(_BackupTargetEdit, "BackupTargetUpdate")


class BackupTargetRead(ReadSchema):
    name: str
    type: str
    enabled: bool
    host: str
    port: int | None = None
    share: str | None = None
    folder: str
    username: str
    keep_days: int
    include_key: bool
    description: str | None = None
    has_secret: bool
    has_private_key: bool
    host_key: str | None = None
    last_copy_at: datetime | None = None
    last_error: str | None = None
    last_error_at: datetime | None = None


class FileName(InputSchema):
    file: str = Field(..., min_length=1, max_length=255)


class SecretsKey(InputSchema):
    key: str = Field(..., min_length=1, max_length=200)
