from fastapi import APIRouter, Depends
from sqlalchemy import func

from app.api import alerts, auth, discovery, extra, history
from app.api.auth import require_admin, require_user
from app.api.crud import build_crud_router
from app.models import (
    AlertChannel,
    VLAN,
    VRF,
    Cable,
    Device,
    DeviceRole,
    DeviceType,
    DiscoveryJob,
    Interface,
    IPAddress,
    Location,
    Manufacturer,
    NetworkMap,
    Prefix,
    Rack,
    Site,
    SnmpProfile,
    StackMember,
    User,
)
from app.schemas import alerts as al
from app.schemas import auth as sa
from app.schemas import dcim as d
from app.schemas import discovery as sd
from app.schemas import ipam as i
from app.schemas import maps as m
from app.services import rules

api_router = APIRouter(prefix="/api")
# Tutto quello che non è login richiede un utente; per scrivere serve il ruolo editor o admin
protected = APIRouter(dependencies=[Depends(require_user)])

_routers = [
    # ---------- Infrastruttura ----------
    dict(model=Site, create_schema=d.SiteCreate, update_schema=d.SiteUpdate, read_schema=d.SiteRead,
         path="/sites", tag="Sedi", search=("name", "address"), order_by=(Site.name,)),
    dict(model=Location, create_schema=d.LocationCreate, update_schema=d.LocationUpdate, read_schema=d.LocationRead,
         path="/locations", tag="Posizioni", filters=("site_id", "parent_id"), search=("name", "path"),
         order_by=(Location.site_id, func.lower(Location.path), Location.id), hook=rules.location_hook),  # albero per sede
    dict(model=Rack, create_schema=d.RackCreate, update_schema=d.RackUpdate, read_schema=d.RackRead,
         path="/racks", tag="Rack", filters=("site_id", "location_id"), search=("name",),
         order_by=(Rack.name,), hook=rules.rack_hook),
    dict(model=Manufacturer, create_schema=d.ManufacturerCreate, update_schema=d.ManufacturerUpdate,
         read_schema=d.ManufacturerRead, path="/manufacturers", tag="Produttori", search=("name",),
         order_by=(Manufacturer.name,)),
    dict(model=DeviceType, create_schema=d.DeviceTypeCreate, update_schema=d.DeviceTypeUpdate,
         read_schema=d.DeviceTypeRead, path="/device-types", tag="Modelli", filters=("manufacturer_id",),
         search=("model", "part_number"), order_by=(DeviceType.model,), hook=rules.device_type_hook),
    dict(model=DeviceRole, create_schema=d.DeviceRoleCreate, update_schema=d.DeviceRoleUpdate,
         read_schema=d.DeviceRoleRead, path="/device-roles", tag="Ruoli", search=("name",),
         order_by=(DeviceRole.level, DeviceRole.name)),
    dict(model=Device, create_schema=d.DeviceCreate, update_schema=d.DeviceUpdate, read_schema=d.DeviceRead,
         path="/devices", tag="Device",
         filters=("site_id", "location_id", "rack_id", "role_id", "device_type_id", "status", "source", "reachable"),
         search=("name", "serial", "asset_tag", "sys_name", "management_ip"), order_by=(Device.name,), hook=rules.device_hook,
         delete_hook=rules.device_delete_hook),
    dict(model=Interface, create_schema=d.InterfaceCreate, update_schema=d.InterfaceUpdate,
         read_schema=d.InterfaceRead, path="/interfaces", tag="Interfacce",
         filters=("device_id", "type", "mode", "enabled", "untagged_vlan_id", "source"),
         search=("name", "mac_address", "description"), order_by=(Interface.device_id, Interface.name),
         hook=rules.interface_hook),
    dict(model=StackMember, create_schema=d.StackMemberCreate, update_schema=d.StackMemberUpdate,
         read_schema=d.StackMemberRead, path="/stack-members", tag="Stack", filters=("device_id",),
         search=("serial", "model"), order_by=(StackMember.device_id, StackMember.number), hook=rules.stack_member_hook),
    dict(model=Cable, create_schema=d.CableCreate, update_schema=d.CableUpdate, read_schema=d.CableRead,
         path="/cables", tag="Cavi", filters=("status", "type", "source"), search=("label", "description"),
         hook=rules.cable_hook),
    # ---------- IPAM ----------
    dict(model=VRF, create_schema=i.VRFCreate, update_schema=i.VRFUpdate, read_schema=i.VRFRead,
         path="/vrfs", tag="VRF", search=("name", "rd"), order_by=(VRF.name,)),
    dict(model=VLAN, create_schema=i.VLANCreate, update_schema=i.VLANUpdate, read_schema=i.VLANRead,
         path="/vlans", tag="VLAN", filters=("site_id", "vid", "status"), search=("name",),
         order_by=(VLAN.vid,), hook=rules.vlan_hook),
    dict(model=Prefix, create_schema=i.PrefixCreate, update_schema=i.PrefixUpdate, read_schema=i.PrefixRead,
         path="/prefixes", tag="Prefissi", filters=("vrf_id", "site_id", "vlan_id", "status"),
         search=("prefix", "description"), order_by=(Prefix.sort_key,), hook=rules.prefix_hook),
    dict(model=IPAddress, create_schema=i.IPAddressCreate, update_schema=i.IPAddressUpdate,
         read_schema=i.IPAddressRead, path="/ip-addresses", tag="Indirizzi IP",
         filters=("vrf_id", "interface_id", "status", "is_primary", "source"),
         search=("host", "dns_name", "description"), order_by=(IPAddress.sort_key,), hook=rules.ip_hook),
    # ---------- Mappe ----------
    dict(model=NetworkMap, create_schema=m.MapCreate, update_schema=m.MapUpdate, read_schema=m.MapRead,
         path="/maps", tag="Mappe", filters=("site_id",), search=("name",), order_by=(NetworkMap.name,),
         hook=rules.map_hook),
    # ---------- Scansione SNMP ----------
    dict(model=SnmpProfile, create_schema=sd.SnmpProfileCreate, update_schema=sd.SnmpProfileUpdate,
         read_schema=sd.SnmpProfileRead, path="/snmp-profiles", tag="Scansione", search=("name", "username"),
         order_by=(SnmpProfile.name,), hook=rules.snmp_profile_hook),
    dict(model=DiscoveryJob, create_schema=sd.DiscoveryJobCreate, update_schema=sd.DiscoveryJobUpdate,
         read_schema=sd.DiscoveryJobRead, path="/discovery-jobs", tag="Scansione", filters=("site_id", "enabled"),
         search=("name", "description"), order_by=(DiscoveryJob.name,), hook=rules.discovery_job_hook),
    # ---------- Utenti (solo amministratori) ----------
    dict(model=User, create_schema=sa.UserCreate, update_schema=sa.UserUpdate, read_schema=sa.UserRead,
         path="/users", tag="Utenti", filters=("role", "active"), search=("username", "full_name"),
         order_by=(User.username,), hook=rules.user_hook, delete_hook=rules.user_delete_hook,
         dependencies=[Depends(require_admin)]),
    # ---------- Avvisi (solo amministratori) ----------
    dict(model=AlertChannel, create_schema=al.AlertChannelCreate, update_schema=al.AlertChannelUpdate,
         read_schema=al.AlertChannelRead, path="/alert-channels", tag="Avvisi", filters=("type", "enabled"),
         search=("name",), order_by=(AlertChannel.name,), hook=rules.alert_channel_hook,
         dependencies=[Depends(require_admin)]),
]

protected.include_router(extra.router)
protected.include_router(discovery.router)
protected.include_router(history.router)
protected.include_router(alerts.router)

for config in _routers:
    protected.include_router(build_crud_router(**config))

api_router.include_router(auth.router)
api_router.include_router(protected)

