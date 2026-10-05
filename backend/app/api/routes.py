from fastapi import APIRouter

from app.api import discovery, extra
from app.api.crud import build_crud_router
from app.models import (
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
)
from app.schemas import dcim as d
from app.schemas import discovery as sd
from app.schemas import ipam as i
from app.schemas import maps as m
from app.services import rules

api_router = APIRouter(prefix="/api")

_routers = [
    # ---------- Infrastruttura ----------
    dict(model=Site, create_schema=d.SiteCreate, update_schema=d.SiteUpdate, read_schema=d.SiteRead,
         path="/sites", tag="Sedi", search=("name", "address"), order_by=(Site.name,)),
    dict(model=Location, create_schema=d.LocationCreate, update_schema=d.LocationUpdate, read_schema=d.LocationRead,
         path="/locations", tag="Posizioni", filters=("site_id", "parent_id"), search=("name",),
         order_by=(Location.name,), hook=rules.location_hook),
    dict(model=Rack, create_schema=d.RackCreate, update_schema=d.RackUpdate, read_schema=d.RackRead,
         path="/racks", tag="Rack", filters=("site_id", "location_id"), search=("name",),
         order_by=(Rack.name,), hook=rules.rack_hook),
    dict(model=Manufacturer, create_schema=d.ManufacturerCreate, update_schema=d.ManufacturerUpdate,
         read_schema=d.ManufacturerRead, path="/manufacturers", tag="Produttori", search=("name",),
         order_by=(Manufacturer.name,)),
    dict(model=DeviceType, create_schema=d.DeviceTypeCreate, update_schema=d.DeviceTypeUpdate,
         read_schema=d.DeviceTypeRead, path="/device-types", tag="Modelli", filters=("manufacturer_id",),
         search=("model", "part_number"), order_by=(DeviceType.model,)),
    dict(model=DeviceRole, create_schema=d.DeviceRoleCreate, update_schema=d.DeviceRoleUpdate,
         read_schema=d.DeviceRoleRead, path="/device-roles", tag="Ruoli", search=("name",),
         order_by=(DeviceRole.level, DeviceRole.name)),
    dict(model=Device, create_schema=d.DeviceCreate, update_schema=d.DeviceUpdate, read_schema=d.DeviceRead,
         path="/devices", tag="Device",
         filters=("site_id", "location_id", "rack_id", "role_id", "device_type_id", "status", "source"),
         search=("name", "serial", "asset_tag", "sys_name"), order_by=(Device.name,), hook=rules.device_hook),
    dict(model=Interface, create_schema=d.InterfaceCreate, update_schema=d.InterfaceUpdate,
         read_schema=d.InterfaceRead, path="/interfaces", tag="Interfacce",
         filters=("device_id", "type", "mode", "enabled", "untagged_vlan_id", "source"),
         search=("name", "mac_address", "description"), order_by=(Interface.device_id, Interface.name),
         hook=rules.interface_hook),
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
]

api_router.include_router(extra.router)
api_router.include_router(discovery.router)

for config in _routers:
    api_router.include_router(build_crud_router(**config))

