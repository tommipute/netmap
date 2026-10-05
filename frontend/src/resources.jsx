/**
 * Configurazione delle entità: colonne della tabella e campi del modulo.
 * Per aggiungere un'entità basta una voce qui (più il backend).
 */
import { Badge, CellLink, Mono } from './components/Bits'
import * as O from './options'

const description = { name: 'description', label: 'Note', type: 'textarea' }
const customFields = { name: 'custom_fields', label: 'Campi personalizzati', type: 'kv' }
const WAIT_SITE = 'Prima scegli la sede'

export const resources = {
  maps: {
    path: 'maps',
    title: 'Mappe',
    newLabel: 'Nuova mappa',
    editLabel: 'Modifica mappa',
    label: (o) => o.name,
    detail: (o) => `/maps/${o.id}`,
    intro: 'Ogni mappa mostra i device di una sede e i cavi che li collegano.',
    filters: [{ name: 'site_id', label: 'Sede', ref: 'sites' }],
    columns: [
      { name: 'name', label: 'Nome' },
      { name: 'site_id', label: 'Sede', type: 'ref', ref: 'sites' },
      { name: 'location_id', label: 'Posizione', type: 'ref', ref: 'locations', empty: 'Tutta la sede' },
      { name: 'auto_include', label: 'Contenuto', render: (o) => (o.auto_include ? 'Tutti i device' : 'Device scelti') },
    ],
    fields: [
      { name: 'name', label: 'Nome', required: true, placeholder: 'Rete sede di Torino' },
      { name: 'site_id', label: 'Sede', type: 'ref', ref: 'sites', required: true, createOnly: true },
      { name: 'location_id', label: 'Posizione', type: 'ref', ref: 'locations', dependsOn: 'site_id', waitLabel: WAIT_SITE, emptyLabel: 'Tutta la sede' },
      {
        name: 'auto_include',
        label: 'Mostra sempre tutti i device',
        type: 'bool',
        default: true,
        help: 'Togli la spunta per scegliere a mano quali device mettere in mappa.',
      },
      description,
    ],
  },

  devices: {
    path: 'devices',
    title: 'Device',
    newLabel: 'Nuovo device',
    editLabel: 'Modifica device',
    label: (o) => o.name,
    detail: (o) => `/devices/${o.id}`,
    filters: [
      { name: 'site_id', label: 'Sede', ref: 'sites' },
      { name: 'role_id', label: 'Ruolo', ref: 'device-roles' },
      { name: 'status', label: 'Stato', options: O.DEVICE_STATUS },
    ],
    columns: [
      { name: 'name', label: 'Nome', render: (o) => <strong>{o.name}</strong> },
      { name: 'status', label: 'Stato', type: 'badge', options: O.DEVICE_STATUS },
      { name: 'role_id', label: 'Ruolo', type: 'ref', ref: 'device-roles' },
      { name: 'site_id', label: 'Sede', type: 'ref', ref: 'sites' },
      { name: 'location_id', label: 'Posizione', type: 'ref', ref: 'locations' },
      { name: 'device_type_id', label: 'Modello', type: 'ref', ref: 'device-types' },
      { name: 'serial', label: 'Seriale', type: 'mono' },
    ],
    fields: [
      { name: 'name', label: 'Nome', required: true, placeholder: 'sw-p1-01' },
      { name: 'status', label: 'Stato', type: 'select', options: O.DEVICE_STATUS, default: 'active', required: true },
      { name: 'site_id', label: 'Sede', type: 'ref', ref: 'sites', required: true },
      { name: 'location_id', label: 'Posizione', type: 'ref', ref: 'locations', dependsOn: 'site_id', waitLabel: WAIT_SITE },
      { name: 'rack_id', label: 'Rack', type: 'ref', ref: 'racks', dependsOn: 'site_id', waitLabel: WAIT_SITE },
      { name: 'rack_position', label: 'Unità nel rack (U)', type: 'number', showIf: (v) => !!v.rack_id, hiddenValue: null },
      { name: 'role_id', label: 'Ruolo', type: 'ref', ref: 'device-roles' },
      { name: 'device_type_id', label: 'Modello', type: 'ref', ref: 'device-types' },
      { name: 'serial', label: 'Numero di serie' },
      { name: 'asset_tag', label: 'Asset tag' },
      description,
      customFields,
    ],
  },

  interfaces: {
    path: 'interfaces',
    title: 'Interfacce',
    newLabel: 'Nuova interfaccia',
    editLabel: 'Modifica interfaccia',
    label: (o) => (o.device_name ? `${o.device_name} ${o.name}` : o.name),
    filters: [
      { name: 'device_id', label: 'Device', ref: 'devices' },
      { name: 'type', label: 'Tipo', options: O.INTERFACE_TYPES },
    ],
    columns: [
      { name: 'device_id', label: 'Device', render: (o) => <CellLink to={`/devices/${o.device_id}`}>{o.device_name}</CellLink> },
      { name: 'name', label: 'Porta', type: 'mono' },
      { name: 'type', label: 'Tipo', type: 'select', options: O.INTERFACE_TYPES },
      { name: 'mode', label: 'VLAN', type: 'select', options: O.INTERFACE_MODES },
      { name: 'speed_mbps', label: 'Velocità', render: (o) => O.formatSpeed(o.speed_mbps) },
      { name: 'mac_address', label: 'MAC', type: 'mono' },
      { name: 'enabled', label: 'Abilitata', type: 'bool' },
    ],
    fields: [
      { name: 'device_id', label: 'Device', type: 'ref', ref: 'devices', required: true, createOnly: true },
      { name: 'name', label: 'Nome porta', required: true, placeholder: 'Gi1/0/1' },
      { name: 'type', label: 'Tipo', type: 'select', options: O.INTERFACE_TYPES, default: 'copper', required: true },
      { name: 'speed_mbps', label: 'Velocità (Mbps)', type: 'number', placeholder: '1000' },
      { name: 'mode', label: 'Modalità VLAN', type: 'select', options: O.INTERFACE_MODES, emptyLabel: 'Nessuna (routed)' },
      {
        name: 'untagged_vlan_id',
        label: 'VLAN',
        type: 'ref',
        ref: 'vlans',
        showIf: (v) => !!v.mode,
        hiddenValue: null,
        help: 'Su un trunk è la VLAN nativa.',
      },
      { name: 'tagged_vlan_ids', label: 'VLAN tagged', type: 'refmulti', ref: 'vlans', showIf: (v) => v.mode === 'trunk', hiddenValue: [] },
      { name: 'mac_address', label: 'MAC address', placeholder: 'aa:bb:cc:dd:ee:ff' },
      { name: 'mtu', label: 'MTU', type: 'number' },
      { name: 'lag_id', label: 'Fa parte del LAG', type: 'ref', ref: 'interfaces', dependsOn: 'device_id', params: { type: 'lag' }, emptyLabel: 'Nessuno' },
      { name: 'enabled', label: 'Abilitata', type: 'bool', default: true },
      { name: 'mgmt_only', label: 'Solo management', type: 'bool' },
      description,
      customFields,
    ],
  },

  cables: {
    path: 'cables',
    title: 'Cavi',
    newLabel: 'Nuovo cavo',
    editLabel: 'Modifica cavo',
    label: (o) => `${o.a_device_name} ${o.a_interface_name} – ${o.b_device_name} ${o.b_interface_name}`,
    filters: [
      { name: 'type', label: 'Tipo', options: O.CABLE_TYPES },
      { name: 'status', label: 'Stato', options: O.CABLE_STATUS },
    ],
    columns: [
      {
        name: 'a',
        label: 'Lato A',
        render: (o) => (
          <>
            <CellLink to={`/devices/${o.a_device_id}`}>{o.a_device_name}</CellLink> <Mono>{o.a_interface_name}</Mono>
          </>
        ),
      },
      {
        name: 'b',
        label: 'Lato B',
        render: (o) => (
          <>
            <CellLink to={`/devices/${o.b_device_id}`}>{o.b_device_name}</CellLink> <Mono>{o.b_interface_name}</Mono>
          </>
        ),
      },
      { name: 'type', label: 'Tipo', type: 'select', options: O.CABLE_TYPES },
      { name: 'status', label: 'Stato', type: 'badge', options: O.CABLE_STATUS },
      { name: 'label', label: 'Etichetta', type: 'mono' },
    ],
    fields: [
      { name: 'a_interface_id', label: 'Lato A', type: 'interface', required: true, freeOnly: true },
      { name: 'b_interface_id', label: 'Lato B', type: 'interface', required: true, freeOnly: true },
      { name: 'type', label: 'Tipo cavo', type: 'select', options: O.CABLE_TYPES },
      { name: 'status', label: 'Stato', type: 'select', options: O.CABLE_STATUS, default: 'connected', required: true },
      { name: 'label', label: 'Etichetta', placeholder: 'C-0142' },
      { name: 'color', label: 'Colore', type: 'color' },
      { name: 'length', label: 'Lunghezza', type: 'number' },
      { name: 'length_unit', label: 'Unità', type: 'select', options: O.LENGTH_UNITS, default: 'm', required: true },
      description,
      customFields,
    ],
  },

  sites: {
    path: 'sites',
    title: 'Sedi',
    newLabel: 'Nuova sede',
    editLabel: 'Modifica sede',
    label: (o) => o.name,
    columns: [
      { name: 'name', label: 'Nome', render: (o) => <strong>{o.name}</strong> },
      { name: 'address', label: 'Indirizzo' },
      { name: 'description', label: 'Note' },
    ],
    fields: [
      { name: 'name', label: 'Nome', required: true },
      { name: 'address', label: 'Indirizzo' },
      description,
      customFields,
    ],
  },

  locations: {
    path: 'locations',
    title: 'Posizioni',
    newLabel: 'Nuova posizione',
    editLabel: 'Modifica posizione',
    intro: 'Edifici, piani e stanze. Una posizione può stare dentro un\'altra.',
    label: (o) => o.name,
    filters: [{ name: 'site_id', label: 'Sede', ref: 'sites' }],
    columns: [
      { name: 'name', label: 'Nome', render: (o) => <strong>{o.name}</strong> },
      { name: 'site_id', label: 'Sede', type: 'ref', ref: 'sites' },
      { name: 'parent_id', label: 'Dentro a', type: 'ref', ref: 'locations' },
    ],
    fields: [
      { name: 'name', label: 'Nome', required: true, placeholder: 'Primo piano' },
      { name: 'site_id', label: 'Sede', type: 'ref', ref: 'sites', required: true, createOnly: true },
      { name: 'parent_id', label: 'Dentro a', type: 'ref', ref: 'locations', dependsOn: 'site_id', waitLabel: WAIT_SITE, emptyLabel: 'Nessuna (livello principale)' },
      description,
      customFields,
    ],
  },

  racks: {
    path: 'racks',
    title: 'Rack',
    newLabel: 'Nuovo rack',
    editLabel: 'Modifica rack',
    label: (o) => o.name,
    filters: [{ name: 'site_id', label: 'Sede', ref: 'sites' }],
    columns: [
      { name: 'name', label: 'Nome', render: (o) => <strong>{o.name}</strong> },
      { name: 'site_id', label: 'Sede', type: 'ref', ref: 'sites' },
      { name: 'location_id', label: 'Posizione', type: 'ref', ref: 'locations' },
      { name: 'u_height', label: 'Altezza (U)' },
    ],
    fields: [
      { name: 'name', label: 'Nome', required: true, placeholder: 'R01' },
      { name: 'site_id', label: 'Sede', type: 'ref', ref: 'sites', required: true, createOnly: true },
      { name: 'location_id', label: 'Posizione', type: 'ref', ref: 'locations', dependsOn: 'site_id', waitLabel: WAIT_SITE },
      { name: 'u_height', label: 'Altezza (U)', type: 'number', default: 42 },
      description,
      customFields,
    ],
  },

  'device-roles': {
    path: 'device-roles',
    title: 'Ruoli',
    newLabel: 'Nuovo ruolo',
    editLabel: 'Modifica ruolo',
    intro: 'Il colore e il livello decidono come appaiono i device nella mappa automatica.',
    label: (o) => o.name,
    columns: [
      { name: 'name', label: 'Nome', render: (o) => <strong>{o.name}</strong> },
      { name: 'color', label: 'Colore', type: 'color' },
      { name: 'level', label: 'Livello in mappa' },
    ],
    fields: [
      { name: 'name', label: 'Nome', required: true, placeholder: 'Switch di accesso' },
      { name: 'color', label: 'Colore', type: 'color', default: '#888780' },
      { name: 'level', label: 'Livello in mappa', type: 'number', default: 2, help: '0 = riga più in alto (firewall, core), poi 1, 2…' },
      description,
    ],
  },

  'device-types': {
    path: 'device-types',
    title: 'Modelli',
    newLabel: 'Nuovo modello',
    editLabel: 'Modifica modello',
    label: (o) => o.model,
    filters: [{ name: 'manufacturer_id', label: 'Produttore', ref: 'manufacturers' }],
    columns: [
      { name: 'model', label: 'Modello', render: (o) => <strong>{o.model}</strong> },
      { name: 'manufacturer_id', label: 'Produttore', type: 'ref', ref: 'manufacturers' },
      { name: 'part_number', label: 'Part number', type: 'mono' },
      { name: 'u_height', label: 'Altezza (U)' },
    ],
    fields: [
      { name: 'manufacturer_id', label: 'Produttore', type: 'ref', ref: 'manufacturers', required: true },
      { name: 'model', label: 'Modello', required: true, placeholder: 'Catalyst 9300-48P' },
      { name: 'part_number', label: 'Part number' },
      { name: 'u_height', label: 'Altezza (U)', type: 'number', default: 1 },
      { name: 'sys_object_id', label: 'sysObjectID SNMP', help: 'Serve alla scansione per riconoscere il modello.' },
      description,
      customFields,
    ],
  },

  manufacturers: {
    path: 'manufacturers',
    title: 'Produttori',
    newLabel: 'Nuovo produttore',
    editLabel: 'Modifica produttore',
    label: (o) => o.name,
    columns: [{ name: 'name', label: 'Nome', render: (o) => <strong>{o.name}</strong> }],
    fields: [{ name: 'name', label: 'Nome', required: true }],
  },

  prefixes: {
    path: 'prefixes',
    title: 'Subnet',
    newLabel: 'Nuova subnet',
    editLabel: 'Modifica subnet',
    label: (o) => o.prefix,
    detail: (o) => `/prefixes/${o.id}`,
    filters: [
      { name: 'site_id', label: 'Sede', ref: 'sites' },
      { name: 'vrf_id', label: 'VRF', ref: 'vrfs' },
    ],
    columns: [
      { name: 'prefix', label: 'Subnet', render: (o) => <span className="mono strong">{o.prefix}</span> },
      { name: 'status', label: 'Stato', type: 'badge', options: O.IPAM_STATUS },
      { name: 'vlan_id', label: 'VLAN', type: 'ref', ref: 'vlans' },
      { name: 'site_id', label: 'Sede', type: 'ref', ref: 'sites' },
      { name: 'vrf_id', label: 'VRF', type: 'ref', ref: 'vrfs', empty: 'Globale' },
      { name: 'description', label: 'Note' },
    ],
    fields: [
      { name: 'prefix', label: 'Subnet', required: true, placeholder: '10.10.10.0/24' },
      { name: 'status', label: 'Stato', type: 'select', options: O.IPAM_STATUS, default: 'active', required: true },
      { name: 'site_id', label: 'Sede', type: 'ref', ref: 'sites' },
      { name: 'vlan_id', label: 'VLAN', type: 'ref', ref: 'vlans' },
      { name: 'vrf_id', label: 'VRF', type: 'ref', ref: 'vrfs', emptyLabel: 'Globale' },
      description,
      customFields,
    ],
  },

  'ip-addresses': {
    path: 'ip-addresses',
    title: 'Indirizzi IP',
    newLabel: 'Nuovo indirizzo IP',
    editLabel: 'Modifica indirizzo IP',
    label: (o) => o.address,
    filters: [
      { name: 'status', label: 'Stato', options: O.IP_STATUS },
      { name: 'vrf_id', label: 'VRF', ref: 'vrfs' },
    ],
    columns: [
      { name: 'address', label: 'Indirizzo', render: (o) => <span className="mono strong">{o.address}</span> },
      {
        name: 'interface_id',
        label: 'Assegnato a',
        render: (o) =>
          o.device_id ? (
            <>
              <CellLink to={`/devices/${o.device_id}`}>{o.device_name}</CellLink> <Mono>{o.interface_name}</Mono>
              {o.is_primary && <span className="tag">management</span>}
            </>
          ) : (
            <span className="muted">Libero</span>
          ),
      },
      { name: 'dns_name', label: 'Nome DNS', type: 'mono' },
      { name: 'status', label: 'Stato', type: 'badge', options: O.IP_STATUS },
    ],
    fields: [
      { name: 'address', label: 'Indirizzo con maschera', required: true, placeholder: '10.10.10.25/24' },
      { name: 'status', label: 'Stato', type: 'select', options: O.IP_STATUS, default: 'active', required: true },
      { name: 'interface_id', label: 'Interfaccia', type: 'interface' },
      {
        name: 'is_primary',
        label: 'IP di management del device',
        type: 'bool',
        showIf: (v) => !!v.interface_id,
        hiddenValue: false,
      },
      { name: 'dns_name', label: 'Nome DNS' },
      { name: 'vrf_id', label: 'VRF', type: 'ref', ref: 'vrfs', emptyLabel: 'Globale' },
      description,
      customFields,
    ],
  },

  vlans: {
    path: 'vlans',
    title: 'VLAN',
    newLabel: 'Nuova VLAN',
    editLabel: 'Modifica VLAN',
    label: (o) => `${o.vid} ${o.name}`,
    filters: [{ name: 'site_id', label: 'Sede', ref: 'sites' }],
    columns: [
      { name: 'vid', label: 'ID', render: (o) => <span className="mono strong">{o.vid}</span> },
      { name: 'name', label: 'Nome' },
      { name: 'site_id', label: 'Sede', type: 'ref', ref: 'sites', empty: 'Tutte le sedi' },
      { name: 'status', label: 'Stato', type: 'badge', options: O.IPAM_STATUS },
    ],
    fields: [
      { name: 'vid', label: 'ID VLAN', type: 'number', required: true, placeholder: '10' },
      { name: 'name', label: 'Nome', required: true, placeholder: 'Uffici' },
      { name: 'site_id', label: 'Sede', type: 'ref', ref: 'sites', emptyLabel: 'Tutte le sedi' },
      { name: 'status', label: 'Stato', type: 'select', options: O.IPAM_STATUS, default: 'active', required: true },
      description,
      customFields,
    ],
  },

  vrfs: {
    path: 'vrfs',
    title: 'VRF',
    newLabel: 'Nuova VRF',
    editLabel: 'Modifica VRF',
    label: (o) => o.name,
    columns: [
      { name: 'name', label: 'Nome', render: (o) => <strong>{o.name}</strong> },
      { name: 'rd', label: 'Route distinguisher', type: 'mono' },
      { name: 'description', label: 'Note' },
    ],
    fields: [
      { name: 'name', label: 'Nome', required: true },
      { name: 'rd', label: 'Route distinguisher', placeholder: '65000:1' },
      description,
      customFields,
    ],
  },
}

export const NAV = [
  { title: 'Rete', items: ['maps', 'devices', 'interfaces', 'cables'] },
  { title: 'Luoghi', items: ['sites', 'locations', 'racks'] },
  { title: 'Indirizzamento', items: ['prefixes', 'ip-addresses', 'vlans', 'vrfs'] },
  { title: 'Catalogo', items: ['device-roles', 'device-types', 'manufacturers'] },
]
