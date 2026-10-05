from typing import Any, Literal

from pydantic import Field, model_validator

from app.models.enums import CableStatus, CableType, DeviceStatus, InterfaceMode, InterfaceType
from app.schemas.common import (
    DiscoveryRead,
    HexColor,
    InputSchema,
    MacAddress,
    Name,
    ReadSchema,
    make_partial,
)

# Convenzione: XBase = campi modificabili, XCreate = + campi fissi dopo la creazione,
# XUpdate = XBase tutto opzionale (PATCH), XRead = risposta dell'API.


# ---------- Sedi ----------
class SiteBase(InputSchema):
    name: Name
    address: str | None = Field(None, max_length=255)
    description: str | None = None
    custom_fields: dict[str, Any] = Field(default_factory=dict)


class SiteCreate(SiteBase):
    pass


SiteUpdate = make_partial(SiteBase, "SiteUpdate")


class SiteRead(SiteCreate, ReadSchema):
    pass


# ---------- Posizioni (edificio/piano/stanza) ----------
class LocationBase(InputSchema):
    name: Name
    parent_id: int | None = None
    description: str | None = None
    custom_fields: dict[str, Any] = Field(default_factory=dict)


class LocationCreate(LocationBase):
    site_id: int


LocationUpdate = make_partial(LocationBase, "LocationUpdate")


class LocationRead(LocationCreate, ReadSchema):
    pass


# ---------- Rack ----------
class RackBase(InputSchema):
    name: Name
    location_id: int | None = None
    u_height: int = Field(42, ge=1, le=60)
    description: str | None = None
    custom_fields: dict[str, Any] = Field(default_factory=dict)


class RackCreate(RackBase):
    site_id: int


RackUpdate = make_partial(RackBase, "RackUpdate")


class RackRead(RackCreate, ReadSchema):
    pass


# ---------- Produttori ----------
class ManufacturerBase(InputSchema):
    name: Name


class ManufacturerCreate(ManufacturerBase):
    pass


ManufacturerUpdate = make_partial(ManufacturerBase, "ManufacturerUpdate")


class ManufacturerRead(ManufacturerCreate, ReadSchema):
    pass


# ---------- Modelli di device ----------
class DeviceTypeBase(InputSchema):
    manufacturer_id: int
    model: Name
    part_number: str | None = Field(None, max_length=100)
    u_height: int = Field(1, ge=0, le=60)
    sys_object_id: str | None = Field(
        None, max_length=255, description="sysObjectID SNMP, per riconoscere il modello in automatico"
    )
    description: str | None = None
    custom_fields: dict[str, Any] = Field(default_factory=dict)


class DeviceTypeCreate(DeviceTypeBase):
    pass


DeviceTypeUpdate = make_partial(DeviceTypeBase, "DeviceTypeUpdate")


class DeviceTypeRead(DeviceTypeCreate, ReadSchema):
    pass


# ---------- Ruoli ----------
class DeviceRoleBase(InputSchema):
    name: Name
    color: HexColor = "#888780"
    level: int = Field(
        2, ge=0, le=9, description="Livello nella mappa gerarchica: 0 = in alto (firewall/core), più alto = più in basso"
    )
    description: str | None = None


class DeviceRoleCreate(DeviceRoleBase):
    pass


DeviceRoleUpdate = make_partial(DeviceRoleBase, "DeviceRoleUpdate")


class DeviceRoleRead(DeviceRoleCreate, ReadSchema):
    pass


# ---------- Device ----------
class DeviceBase(InputSchema):
    name: Name
    site_id: int
    location_id: int | None = None
    rack_id: int | None = None
    rack_position: int | None = Field(None, ge=1, le=60)
    device_type_id: int | None = None
    role_id: int | None = None
    status: DeviceStatus = DeviceStatus.ACTIVE
    serial: str | None = Field(None, max_length=100)
    asset_tag: str | None = Field(None, max_length=100)
    sys_name: str | None = Field(None, max_length=255)
    sys_descr: str | None = None
    description: str | None = None
    custom_fields: dict[str, Any] = Field(default_factory=dict)


class DeviceCreate(DeviceBase):
    pass


DeviceUpdate = make_partial(DeviceBase, "DeviceUpdate")


class DeviceRead(DeviceCreate, DiscoveryRead, ReadSchema):
    pass


# ---------- Interfacce ----------
class InterfaceBase(InputSchema):
    name: Name
    type: InterfaceType = InterfaceType.COPPER
    enabled: bool = True
    mgmt_only: bool = False
    mac_address: MacAddress | None = None
    speed_mbps: int | None = Field(None, ge=0)
    mtu: int | None = Field(None, ge=64, le=65535)
    mode: InterfaceMode | None = Field(None, description="access / trunk, vuoto = interfaccia routed")
    untagged_vlan_id: int | None = None
    tagged_vlan_ids: list[int] = Field(default_factory=list, description="Solo con mode = trunk")
    lag_id: int | None = Field(None, description="Interfaccia LAG (port-channel) di cui fa parte")
    description: str | None = None
    custom_fields: dict[str, Any] = Field(default_factory=dict)


class InterfaceCreate(InterfaceBase):
    device_id: int


InterfaceUpdate = make_partial(InterfaceBase, "InterfaceUpdate")


class InterfaceRead(InterfaceCreate, DiscoveryRead, ReadSchema):
    device_name: str | None = None
    if_index: int | None = None
    oper_status: str | None = None


# ---------- Cavi ----------
class CableBase(InputSchema):
    a_interface_id: int
    b_interface_id: int
    type: CableType | None = None
    status: CableStatus = CableStatus.CONNECTED
    label: str | None = Field(None, max_length=100)
    color: HexColor | None = None
    length: float | None = Field(None, gt=0)
    length_unit: Literal["m", "cm", "ft"] = "m"
    description: str | None = None
    custom_fields: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _distinct_ends(self):
        if self.a_interface_id == self.b_interface_id:
            raise ValueError("Le due estremità del cavo devono essere interfacce diverse")
        return self


class CableCreate(CableBase):
    pass


CableUpdate = make_partial(CableBase, "CableUpdate")


class CableRead(CableCreate, DiscoveryRead, ReadSchema):
    a_device_id: int
    a_device_name: str
    a_interface_name: str
    b_device_id: int
    b_device_name: str
    b_interface_name: str
