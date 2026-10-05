from typing import Any

from pydantic import Field

from app.models.enums import IPAddressStatus, IPAMStatus
from app.schemas.common import (
    DiscoveryRead,
    InputSchema,
    IPInterfaceStr,
    Name,
    PrefixStr,
    ReadSchema,
    make_partial,
)


# ---------- VRF ----------
class VRFBase(InputSchema):
    name: Name
    rd: str | None = Field(None, max_length=50, description="Route distinguisher, es. 65000:1")
    description: str | None = None
    custom_fields: dict[str, Any] = Field(default_factory=dict)


class VRFCreate(VRFBase):
    pass


VRFUpdate = make_partial(VRFBase, "VRFUpdate")


class VRFRead(VRFCreate, ReadSchema):
    pass


# ---------- VLAN ----------
class VLANBase(InputSchema):
    vid: int = Field(..., ge=1, le=4094)
    name: Name
    site_id: int | None = Field(None, description="Vuoto = VLAN globale")
    status: IPAMStatus = IPAMStatus.ACTIVE
    description: str | None = None
    custom_fields: dict[str, Any] = Field(default_factory=dict)


class VLANCreate(VLANBase):
    pass


VLANUpdate = make_partial(VLANBase, "VLANUpdate")


class VLANRead(VLANCreate, ReadSchema):
    pass


# ---------- Prefissi ----------
class PrefixBase(InputSchema):
    prefix: PrefixStr = Field(..., description="Es. 10.0.0.0/24 (viene normalizzato)")
    vrf_id: int | None = None
    site_id: int | None = None
    vlan_id: int | None = None
    status: IPAMStatus = IPAMStatus.ACTIVE
    description: str | None = None
    custom_fields: dict[str, Any] = Field(default_factory=dict)


class PrefixCreate(PrefixBase):
    pass


PrefixUpdate = make_partial(PrefixBase, "PrefixUpdate")


class PrefixRead(PrefixCreate, ReadSchema):
    pass


# ---------- Indirizzi IP ----------
class IPAddressBase(InputSchema):
    address: IPInterfaceStr = Field(..., description="Indirizzo con maschera, es. 10.0.0.5/24")
    vrf_id: int | None = None
    interface_id: int | None = None
    is_primary: bool = Field(False, description="IP principale (management) del device")
    status: IPAddressStatus = IPAddressStatus.ACTIVE
    dns_name: str | None = Field(None, max_length=255)
    description: str | None = None
    custom_fields: dict[str, Any] = Field(default_factory=dict)


class IPAddressCreate(IPAddressBase):
    pass


IPAddressUpdate = make_partial(IPAddressBase, "IPAddressUpdate")


class IPAddressRead(IPAddressCreate, DiscoveryRead, ReadSchema):
    host: str
    interface_name: str | None = None
    device_id: int | None = None
    device_name: str | None = None
