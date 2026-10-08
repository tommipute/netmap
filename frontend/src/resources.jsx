/**
 * Configurazione delle entità: colonne della tabella e campi del modulo.
 * Per aggiungere un'entità basta una voce qui (più il backend).
 */
import { ROLES } from './auth'
import AlertTestButton from './components/AlertTestButton'
import { Badge, CellLink, LiveStatus, Mono } from './components/Bits'
import RefLabel from './components/RefLabel'
import * as O from './options'
import { LANGUAGES, t, tc, tServer } from './i18n'

const description = { name: 'description', label: t('Note'), type: 'textarea' }
const customFields = { name: 'custom_fields', label: t('Campi personalizzati'), type: 'kv' }
const WAIT_SITE = t('Prima scegli la sede')

function LocationName({ location, tree }) {
  const depth = tree ? (location.path || '').split(' › ').length - 1 : 0
  return (
    <span className="tree-name" style={{ '--depth': depth }}>
      {depth > 0 && <span className="tree-name__branch" aria-hidden="true" />}
      <strong>{location.name}</strong>
    </span>
  )
}

export const resources = {
  maps: {
    path: 'maps',
    title: t('Mappe'),
    newLabel: t('Nuova mappa'),
    editLabel: t('Modifica mappa'),
    label: (o) => o.name,
    detail: (o) => `/maps/${o.id}`,
    intro: t('Ogni mappa mostra i device di una sede e i cavi che li collegano.'),
    filters: [{ name: 'site_id', label: t('Sede'), ref: 'sites' }],
    columns: [
      { name: 'name', label: t('Nome') },
      { name: 'site_id', label: t('Sede'), type: 'ref', ref: 'sites' },
      { name: 'location_id', label: t('Posizione'), type: 'ref', ref: 'locations', empty: t('Tutta la sede') },
      { name: 'auto_include', label: t('Contenuto'), render: (o) => (o.auto_include ? t('Tutti i device') : t('Device scelti')) },
    ],
    fields: [
      { name: 'name', label: t('Nome'), required: true, placeholder: t('Rete sede di Torino') },
      { name: 'site_id', label: t('Sede'), type: 'ref', ref: 'sites', required: true, createOnly: true },
      { name: 'location_id', label: t('Posizione'), type: 'ref', ref: 'locations', dependsOn: 'site_id', waitLabel: WAIT_SITE, emptyLabel: t('Tutta la sede') },
      {
        name: 'auto_include',
        label: t('Mostra sempre tutti i device'),
        type: 'bool',
        default: true,
        help: t('Togli la spunta per scegliere a mano quali device mettere in mappa.'),
      },
      description,
    ],
  },

  devices: {
    path: 'devices',
    title: tc('elenco', 'Device'),
    newLabel: t('Nuovo device'),
    editLabel: t('Modifica device'),
    label: (o) => o.name,
    detail: (o) => `/devices/${o.id}`,
    // Eliminazione: scelta sugli IP (DeleteDialog -> ?with_ips=true)
    deleteOptions: [
      {
        name: 'with_ips',
        label: t('Elimina anche gli IP'),
        default: true,
        help: t('Togli la spunta se gli indirizzi devono restare registrati (liberi) in Indirizzi IP.'),
      },
    ],
    // Modifica in blocco dall'elenco (selezione multipla)
    bulkFields: ['status', 'site_id', 'location_id', 'rack_id', 'role_id', 'device_type_id'],
    filters: [
      { name: 'site_id', label: t('Sede'), ref: 'sites' },
      { name: 'role_id', label: t('Ruolo'), ref: 'device-roles' },
      { name: 'status', label: t('Stato'), options: O.DEVICE_STATUS },
      { name: 'reachable', label: t('Stato live'), options: O.REACHABLE },
    ],
    // Colonne: hidden = da scegliere in "Colonne della tabella"; filter/sortField per le colonne con render
    columns: [
      { name: 'name', label: t('Nome'), render: (o) => <strong>{o.name}</strong>, filter: { kind: 'text' }, sortField: 'name' },
      { name: 'status', label: t('Stato'), type: 'badge', options: O.DEVICE_STATUS },
      {
        name: 'reachable',
        label: t('Stato live'),
        render: (o) => <LiveStatus device={o} />,
        filter: {
          kind: 'options',
          options: [{ value: 'true', label: t('Risponde') }, { value: 'false', label: t('Non risponde') }],
          emptyLabel: t('Non controllato'),
        },
        sortField: null,
      },
      {
        name: 'management_ip',
        label: t('IP'),
        render: (o) => (o.management_ip ? <Mono>{o.management_ip.split('/')[0]}</Mono> : <span className="muted">—</span>),
        filter: { kind: 'text' },
        sortField: 'management_ip',
      },
      { name: 'role_id', label: t('Ruolo'), type: 'ref', ref: 'device-roles' },
      { name: 'site_id', label: t('Sede'), type: 'ref', ref: 'sites' },
      { name: 'location_id', label: t('Posizione'), type: 'ref', ref: 'locations' },
      {
        name: 'rack_id',
        label: t('Rack'),
        render: (o) =>
          o.rack_id ? (
            <>
              <RefLabel resource="racks" id={o.rack_id} />
              {o.rack_position ? <span className="muted"> · U{o.rack_position}</span> : null}
            </>
          ) : (
            <span className="muted">—</span>
          ),
        filter: { kind: 'ref', ref: 'racks' },
        sortField: null,
      },
      { name: 'device_type_id', label: t('Modello'), type: 'ref', ref: 'device-types' },
      { name: 'serial', label: t('Seriale'), type: 'mono' },
      { name: 'asset_tag', label: t('Asset tag'), type: 'mono', hidden: true },
      { name: 'sys_name', label: t('sysName'), type: 'mono', hidden: true },
      { name: 'source', label: t('Origine'), type: 'select', options: O.SOURCES, hidden: true },
      {
        name: 'last_seen_at',
        label: t('Ultima scansione'),
        render: (o) => (o.last_seen_at ? O.formatDateTime(o.last_seen_at) : <span className="muted">—</span>),
        filter: false,
        sortField: 'last_seen_at',
        hidden: true,
      },
      { name: 'description', label: t('Note'), hidden: true },
    ],
    fields: [
      { name: 'name', label: t('Nome'), required: true, placeholder: t('sw-p1-01') },
      { name: 'status', label: t('Stato'), type: 'select', options: O.DEVICE_STATUS, default: 'active', required: true },
      { name: 'site_id', label: t('Sede'), type: 'ref', ref: 'sites', required: true },
      // Nel rack: la posizione è quella del rack (la impone anche il backend)
      { name: 'location_id', label: t('Posizione'), type: 'ref', ref: 'locations', dependsOn: 'site_id', waitLabel: WAIT_SITE,
        fillFrom: { field: 'rack_id', resource: 'racks', key: 'location_id', hint: t('Presa dal rack: il device sta dove sta il rack.') } },
      { name: 'rack_id', label: t('Rack'), type: 'ref', ref: 'racks', dependsOn: 'site_id', waitLabel: WAIT_SITE },
      { name: 'rack_position', label: t('Unità nel rack (U)'), type: 'number', showIf: (v) => !!v.rack_id, hiddenValue: null },
      { name: 'role_id', label: t('Ruolo'), type: 'ref', ref: 'device-roles' },
      { name: 'device_type_id', label: t('Modello'), type: 'ref', ref: 'device-types' },
      {
        name: 'management_ip',
        label: t('IP di management'),
        placeholder: '10.10.99.55/24',
        help: t('Quello per SSH, web e SNMP. Va sulla porta di management (se manca si crea "mgmt"). Vuoto: nessuno.'),
      },
      { name: 'serial', label: t('Numero di serie') },
      { name: 'asset_tag', label: t('Asset tag') },
      description,
      customFields,
    ],
  },

  interfaces: {
    path: 'interfaces',
    title: t('Interfacce'),
    newLabel: t('Nuova interfaccia'),
    editLabel: t('Modifica interfaccia'),
    label: (o) => (o.device_name ? `${o.device_name} ${o.name}` : o.name),
    bulkFields: ['type', 'speed_mbps', 'mode', 'untagged_vlan_id', 'mtu', 'enabled', 'mgmt_only'],
    filters: [
      { name: 'device_id', label: t('Device'), ref: 'devices' },
      { name: 'type', label: t('Tipo'), options: O.INTERFACE_TYPES },
    ],
    columns: [
      { name: 'device_id', label: t('Device'), render: (o) => <CellLink to={`/devices/${o.device_id}`}>{o.device_name}</CellLink> },
      { name: 'name', label: t('Porta'), type: 'mono' },
      { name: 'type', label: t('Tipo'), type: 'select', options: O.INTERFACE_TYPES },
      { name: 'mode', label: t('VLAN'), type: 'select', options: O.INTERFACE_MODES },
      { name: 'speed_mbps', label: t('Velocità'), render: (o) => O.formatSpeed(o.speed_mbps) },
      { name: 'mac_address', label: t('MAC'), type: 'mono' },
      { name: 'enabled', label: t('Abilitata'), type: 'bool' },
    ],
    fields: [
      { name: 'device_id', label: t('Device'), type: 'ref', ref: 'devices', required: true, createOnly: true },
      { name: 'name', label: t('Nome porta'), required: true, placeholder: t('Gi1/0/1') },
      { name: 'type', label: t('Tipo'), type: 'select', options: O.INTERFACE_TYPES, default: 'copper', required: true },
      { name: 'speed_mbps', label: t('Velocità (Mbps)'), type: 'number', placeholder: '1000' },
      { name: 'mode', label: t('Modalità VLAN'), type: 'select', options: O.INTERFACE_MODES, emptyLabel: t('Nessuna (routed)') },
      {
        name: 'untagged_vlan_id',
        label: t('VLAN'),
        type: 'ref',
        ref: 'vlans',
        showIf: (v) => !!v.mode,
        hiddenValue: null,
        help: t('Su un trunk è la VLAN nativa.'),
      },
      { name: 'tagged_vlan_ids', label: t('VLAN tagged'), type: 'refmulti', ref: 'vlans', showIf: (v) => v.mode === 'trunk', hiddenValue: [] },
      { name: 'mac_address', label: t('MAC address'), placeholder: t('aa:bb:cc:dd:ee:ff') },
      { name: 'mtu', label: t('MTU'), type: 'number' },
      { name: 'lag_id', label: t('Fa parte del LAG'), type: 'ref', ref: 'interfaces', dependsOn: 'device_id', params: { type: 'lag' }, emptyLabel: t('Nessuno') },
      { name: 'enabled', label: t('Abilitata'), type: 'bool', default: true },
      { name: 'mgmt_only', label: t('Solo management'), type: 'bool' },
      description,
      customFields,
    ],
  },

  cables: {
    path: 'cables',
    title: t('Cavi'),
    newLabel: t('Nuovo cavo'),
    editLabel: t('Modifica cavo'),
    label: (o) => `${o.a_device_name} ${o.a_interface_name} – ${o.b_device_name} ${o.b_interface_name}`,
    bulkFields: ['type', 'status', 'color', 'length', 'length_unit'],
    filters: [
      { name: 'type', label: t('Tipo'), options: O.CABLE_TYPES },
      { name: 'status', label: t('Stato'), options: O.CABLE_STATUS },
    ],
    columns: [
      {
        name: 'a',
        label: t('Lato A'),
        render: (o) => (
          <>
            <CellLink to={`/devices/${o.a_device_id}`}>{o.a_device_name}</CellLink> <Mono>{o.a_interface_name}</Mono>
          </>
        ),
      },
      {
        name: 'b',
        label: t('Lato B'),
        render: (o) => (
          <>
            <CellLink to={`/devices/${o.b_device_id}`}>{o.b_device_name}</CellLink> <Mono>{o.b_interface_name}</Mono>
          </>
        ),
      },
      { name: 'type', label: t('Tipo'), type: 'select', options: O.CABLE_TYPES },
      { name: 'status', label: t('Stato'), type: 'badge', options: O.CABLE_STATUS },
      { name: 'label', label: t('Etichetta'), type: 'mono' },
    ],
    fields: [
      { name: 'a_interface_id', label: t('Lato A'), type: 'interface', required: true, freeOnly: true },
      { name: 'b_interface_id', label: t('Lato B'), type: 'interface', required: true, freeOnly: true },
      { name: 'type', label: t('Tipo cavo'), type: 'select', options: O.CABLE_TYPES },
      { name: 'status', label: t('Stato'), type: 'select', options: O.CABLE_STATUS, default: 'connected', required: true },
      { name: 'label', label: t('Etichetta'), placeholder: t('C-0142') },
      { name: 'color', label: t('Colore'), type: 'color' },
      { name: 'length', label: t('Lunghezza'), type: 'number' },
      { name: 'length_unit', label: t('Unità'), type: 'select', options: O.LENGTH_UNITS, default: 'm', required: true },
      description,
      customFields,
    ],
  },

  sites: {
    path: 'sites',
    title: t('Sedi'),
    newLabel: t('Nuova sede'),
    editLabel: t('Modifica sede'),
    label: (o) => o.name,
    columns: [
      { name: 'name', label: t('Nome'), render: (o) => <strong>{o.name}</strong> },
      { name: 'address', label: t('Indirizzo') },
      { name: 'description', label: t('Note') },
    ],
    fields: [
      { name: 'name', label: t('Nome'), required: true },
      { name: 'address', label: t('Indirizzo') },
      description,
      customFields,
    ],
  },

  locations: {
    path: 'locations',
    title: t('Posizioni'),
    newLabel: t('Nuova posizione'),
    editLabel: t('Modifica posizione'),
    intro: t('Edifici, piani e stanze. Una posizione può stare dentro un\'altra.'),
    // Percorso completo ("Palazzina A › P1") nei menu e ovunque compaia la posizione
    label: (o) => o.path || o.name,
    bulkFields: ['parent_id', 'floor'],
    filters: [{ name: 'site_id', label: t('Sede'), ref: 'sites' }],
    columns: [
      // Nell'ordine predefinito (per percorso) ogni posizione sta sotto quella che la contiene, rientrata
      { name: 'name', label: t('Nome'), render: (o, view) => <LocationName location={o} tree={view?.tree} />, filter: { kind: 'text' }, sortField: 'name' },
      { name: 'site_id', label: t('Sede'), type: 'ref', ref: 'sites' },
      { name: 'parent_id', label: t('Dentro a'), type: 'ref', ref: 'locations' },
      { name: 'floor', label: t('Piano (quota)'), hidden: true },
    ],
    fields: [
      { name: 'name', label: t('Nome'), required: true, placeholder: t('Primo piano') },
      { name: 'site_id', label: t('Sede'), type: 'ref', ref: 'sites', required: true, createOnly: true },
      { name: 'parent_id', label: t('Dentro a'), type: 'ref', ref: 'locations', dependsOn: 'site_id', waitLabel: WAIT_SITE, emptyLabel: t('Nessuna (livello principale)') },
      { name: 'floor', label: t('Piano (quota)'), type: 'number', help: t('Per i piani: in mappa quello con il numero più alto sta in cima (es. -1 interrato, 0 terra, 1 primo).') },
      description,
      customFields,
    ],
  },

  racks: {
    path: 'racks',
    title: tc('elenco', 'Rack'),
    newLabel: t('Nuovo rack'),
    editLabel: t('Modifica rack'),
    label: (o) => o.name,
    detail: (o) => `/racks/${o.id}`,
    bulkFields: ['location_id', 'u_height'],
    filters: [{ name: 'site_id', label: t('Sede'), ref: 'sites' }],
    columns: [
      { name: 'name', label: t('Nome'), render: (o) => <strong>{o.name}</strong> },
      { name: 'site_id', label: t('Sede'), type: 'ref', ref: 'sites' },
      { name: 'location_id', label: t('Posizione'), type: 'ref', ref: 'locations' },
      { name: 'u_height', label: t('Altezza (U)') },
    ],
    fields: [
      { name: 'name', label: t('Nome'), required: true, placeholder: t('R01') },
      { name: 'site_id', label: t('Sede'), type: 'ref', ref: 'sites', required: true, createOnly: true },
      { name: 'location_id', label: t('Posizione'), type: 'ref', ref: 'locations', dependsOn: 'site_id', waitLabel: WAIT_SITE },
      { name: 'u_height', label: t('Altezza (U)'), type: 'number', default: 42 },
      description,
      customFields,
    ],
  },

  'device-roles': {
    path: 'device-roles',
    title: t('Ruoli'),
    newLabel: t('Nuovo ruolo'),
    editLabel: t('Modifica ruolo'),
    intro: t('Il colore e il livello decidono come appaiono i device nella mappa automatica.'),
    label: (o) => o.name,
    bulkFields: ['color', 'level'],
    columns: [
      { name: 'name', label: t('Nome'), render: (o) => <strong>{o.name}</strong> },
      { name: 'color', label: t('Colore'), type: 'color' },
      { name: 'level', label: t('Livello in mappa') },
    ],
    fields: [
      { name: 'name', label: t('Nome'), required: true, placeholder: t('Switch di accesso') },
      { name: 'color', label: t('Colore'), type: 'color', default: '#888780' },
      { name: 'level', label: t('Livello in mappa'), type: 'number', default: 2, help: t('0 = riga più in alto (firewall, core), poi 1, 2…') },
      description,
    ],
  },

  'device-types': {
    path: 'device-types',
    title: t('Modelli'),
    newLabel: t('Nuovo modello'),
    editLabel: t('Modifica modello'),
    label: (o) => o.model,
    bulkFields: ['manufacturer_id', 'u_height', 'default_role_id'],
    filters: [{ name: 'manufacturer_id', label: t('Produttore'), ref: 'manufacturers' }],
    columns: [
      { name: 'model', label: t('Modello'), render: (o) => <strong>{o.model}</strong> },
      { name: 'manufacturer_id', label: t('Produttore'), type: 'ref', ref: 'manufacturers' },
      { name: 'part_number', label: t('Part number'), type: 'mono' },
      { name: 'u_height', label: t('Altezza (U)') },
      { name: 'default_role_id', label: t('Ruolo predefinito'), type: 'ref', ref: 'device-roles', empty: '—' },
    ],
    fields: [
      { name: 'manufacturer_id', label: t('Produttore'), type: 'ref', ref: 'manufacturers', required: true },
      { name: 'model', label: t('Modello'), required: true, placeholder: t('Catalyst 9300-48P') },
      { name: 'part_number', label: t('Part number') },
      { name: 'u_height', label: t('Altezza (U)'), type: 'number', default: 1 },
      { name: 'sys_object_id', label: t('sysObjectID SNMP'), help: t('Serve alla scansione per riconoscere il modello.') },
      {
        name: 'default_role_id',
        label: t('Ruolo predefinito'),
        type: 'ref',
        ref: 'device-roles',
        emptyLabel: t('Nessuno'),
        help: t('Lo prendono i device di questo modello senza ruolo: quelli già presenti, i nuovi e quelli trovati dalla scansione.'),
      },
      description,
      customFields,
    ],
  },

  manufacturers: {
    path: 'manufacturers',
    title: t('Produttori'),
    newLabel: t('Nuovo produttore'),
    editLabel: t('Modifica produttore'),
    label: (o) => o.name,
    columns: [{ name: 'name', label: t('Nome'), render: (o) => <strong>{o.name}</strong> }],
    fields: [{ name: 'name', label: t('Nome'), required: true }],
  },

  prefixes: {
    path: 'prefixes',
    title: tc('elenco', 'Subnet'),
    newLabel: t('Nuova subnet'),
    editLabel: t('Modifica subnet'),
    label: (o) => o.prefix,
    detail: (o) => `/prefixes/${o.id}`,
    bulkFields: ['status', 'site_id', 'vlan_id', 'vrf_id'],
    filters: [
      { name: 'site_id', label: t('Sede'), ref: 'sites' },
      { name: 'vrf_id', label: t('VRF'), ref: 'vrfs' },
    ],
    columns: [
      { name: 'prefix', label: t('Subnet'), render: (o) => <span className="mono strong">{o.prefix}</span> },
      { name: 'status', label: t('Stato'), type: 'badge', options: O.IPAM_STATUS },
      { name: 'vlan_id', label: t('VLAN'), type: 'ref', ref: 'vlans' },
      { name: 'site_id', label: t('Sede'), type: 'ref', ref: 'sites' },
      { name: 'vrf_id', label: t('VRF'), type: 'ref', ref: 'vrfs', empty: t('Globale') },
      { name: 'description', label: t('Note') },
    ],
    fields: [
      { name: 'prefix', label: t('Subnet'), required: true, placeholder: '10.10.10.0/24' },
      { name: 'status', label: t('Stato'), type: 'select', options: O.IPAM_STATUS, default: 'active', required: true },
      { name: 'site_id', label: t('Sede'), type: 'ref', ref: 'sites' },
      { name: 'vlan_id', label: t('VLAN'), type: 'ref', ref: 'vlans' },
      { name: 'vrf_id', label: t('VRF'), type: 'ref', ref: 'vrfs', emptyLabel: t('Globale') },
      description,
      customFields,
    ],
  },

  'ip-addresses': {
    path: 'ip-addresses',
    title: t('Indirizzi IP'),
    newLabel: t('Nuovo indirizzo IP'),
    editLabel: t('Modifica indirizzo IP'),
    label: (o) => o.address,
    bulkFields: ['status', 'vrf_id'],
    filters: [
      { name: 'status', label: t('Stato'), options: O.IP_STATUS },
      { name: 'vrf_id', label: t('VRF'), ref: 'vrfs' },
    ],
    columns: [
      { name: 'address', label: t('Indirizzo'), render: (o) => <span className="mono strong">{o.address}</span> },
      {
        name: 'interface_id',
        label: t('Assegnato a'),
        render: (o) =>
          o.device_id ? (
            <>
              <CellLink to={`/devices/${o.device_id}`}>{o.device_name}</CellLink> <Mono>{o.interface_name}</Mono>
              {o.is_primary && <span className="tag">{t('management')}</span>}
            </>
          ) : (
            <span className="muted">{t('Libero')}</span>
          ),
      },
      { name: 'dns_name', label: t('Nome DNS'), type: 'mono' },
      { name: 'status', label: t('Stato'), type: 'badge', options: O.IP_STATUS },
    ],
    fields: [
      { name: 'address', label: t('Indirizzo con maschera'), required: true, placeholder: '10.10.10.25/24' },
      { name: 'status', label: t('Stato'), type: 'select', options: O.IP_STATUS, default: 'active', required: true },
      { name: 'interface_id', label: t('Interfaccia'), type: 'interface' },
      {
        name: 'is_primary',
        label: t('IP di management del device'),
        type: 'bool',
        showIf: (v) => !!v.interface_id,
        hiddenValue: false,
        // Uno solo per device: se il device ne ha già un altro la casella è bloccata
        lockedBy: {
          url: (v) => (v.interface_id ? `/interfaces/${v.interface_id}` : null),
          reason: (iface, v, item) =>
            iface.device_management_ip && !(item?.is_primary && item.interface_id === Number(v.interface_id))
              ? t("{device} ha già l'IP di management {ip}: ce n'è uno solo per device. Per cambiarlo usa il campo nella scheda del device.", { device: iface.device_name, ip: iface.device_management_ip })
              : null,
        },
      },
      { name: 'dns_name', label: t('Nome DNS') },
      { name: 'vrf_id', label: t('VRF'), type: 'ref', ref: 'vrfs', emptyLabel: t('Globale') },
      description,
      customFields,
    ],
  },

  vlans: {
    path: 'vlans',
    title: tc('elenco', 'VLAN'),
    newLabel: t('Nuova VLAN'),
    editLabel: t('Modifica VLAN'),
    label: (o) => `${o.vid} ${o.name}`,
    bulkFields: ['site_id', 'status'],
    filters: [{ name: 'site_id', label: t('Sede'), ref: 'sites' }],
    columns: [
      { name: 'vid', label: t('ID'), render: (o) => <span className="mono strong">{o.vid}</span> },
      { name: 'name', label: t('Nome') },
      { name: 'site_id', label: t('Sede'), type: 'ref', ref: 'sites', empty: t('Tutte le sedi') },
      { name: 'status', label: t('Stato'), type: 'badge', options: O.IPAM_STATUS },
    ],
    fields: [
      { name: 'vid', label: t('ID VLAN'), type: 'number', required: true, placeholder: '10' },
      { name: 'name', label: t('Nome'), required: true, placeholder: t('Uffici') },
      { name: 'site_id', label: t('Sede'), type: 'ref', ref: 'sites', emptyLabel: t('Tutte le sedi') },
      { name: 'status', label: t('Stato'), type: 'select', options: O.IPAM_STATUS, default: 'active', required: true },
      description,
      customFields,
    ],
  },

  vrfs: {
    path: 'vrfs',
    title: tc('elenco', 'VRF'),
    newLabel: t('Nuova VRF'),
    editLabel: t('Modifica VRF'),
    label: (o) => o.name,
    columns: [
      { name: 'name', label: t('Nome'), render: (o) => <strong>{o.name}</strong> },
      { name: 'rd', label: t('Route distinguisher'), type: 'mono' },
      { name: 'description', label: t('Note') },
    ],
    fields: [
      { name: 'name', label: t('Nome'), required: true },
      { name: 'rd', label: t('Route distinguisher'), placeholder: '65000:1' },
      description,
      customFields,
    ],
  },
}

const isV3 = (v) => v.version === 'v3'
const savedSecret = (flag) => (item) => (item?.[flag] ? t('Salvata: lascia vuoto per non cambiarla') : undefined)

Object.assign(resources, {
  'snmp-profiles': {
    path: 'snmp-profiles',
    title: t('Profili SNMP'),
    newLabel: t('Nuovo profilo SNMP'),
    editLabel: t('Modifica profilo SNMP'),
    intro: t('Le credenziali con cui la scansione interroga i device. Community e chiavi sono salvate cifrate e non si possono rileggere.'),
    label: (o) => o.name,
    columns: [
      { name: 'name', label: t('Nome'), render: (o) => <strong>{o.name}</strong> },
      { name: 'version', label: t('Versione'), type: 'select', options: O.SNMP_VERSIONS },
      {
        name: 'credentials',
        label: t('Credenziali'),
        render: (o) =>
          o.version === 'v3' ? (
            <>
              <Mono>{o.username}</Mono>
              {o.auth_protocol && <span className="tag">{o.auth_protocol.toUpperCase()}</span>}
              {o.priv_protocol && <span className="tag">{o.priv_protocol.toUpperCase()}</span>}
            </>
          ) : o.has_community ? (
            t('Community salvata')
          ) : (
            <span className="muted">{t('Manca la community')}</span>
          ),
      },
      { name: 'port', label: t('Porta'), type: 'mono' },
      { name: 'description', label: t('Note') },
    ],
    fields: [
      { name: 'name', label: t('Nome'), required: true, placeholder: t('Switch sede, v2c') },
      { name: 'version', label: t('Versione'), type: 'select', options: O.SNMP_VERSIONS, default: 'v2c', required: true },
      { name: 'community', label: t('Community'), type: 'secret', showIf: (v) => !isV3(v), savedHint: savedSecret('has_community') },
      { name: 'username', label: t('Utente'), showIf: isV3, hiddenValue: undefined },
      { name: 'auth_protocol', label: t('Autenticazione'), type: 'select', options: O.SNMP_AUTH, emptyLabel: t('Nessuna'), showIf: isV3, hiddenValue: undefined },
      { name: 'auth_key', label: t('Chiave di autenticazione'), type: 'secret', showIf: (v) => isV3(v) && !!v.auth_protocol, savedHint: savedSecret('has_auth_key'), help: t('Almeno 8 caratteri.') },
      { name: 'priv_protocol', label: t('Cifratura'), type: 'select', options: O.SNMP_PRIV, emptyLabel: t('Nessuna'), showIf: (v) => isV3(v) && !!v.auth_protocol, hiddenValue: undefined },
      { name: 'priv_key', label: t('Chiave di cifratura'), type: 'secret', showIf: (v) => isV3(v) && !!v.priv_protocol, savedHint: savedSecret('has_priv_key'), help: t('Almeno 8 caratteri.') },
      { name: 'context_name', label: t('Context name'), showIf: isV3, hiddenValue: undefined, help: t('Quasi sempre vuoto.') },
      { name: 'port', label: t('Porta UDP'), type: 'number', default: 161 },
      { name: 'timeout', label: t('Attesa per richiesta (secondi)'), type: 'number', default: 2 },
      { name: 'retries', label: t('Tentativi in più'), type: 'number', default: 1 },
      description,
    ],
  },

  'discovery-jobs': {
    path: 'discovery-jobs',
    title: t('Scansioni'),
    newLabel: t('Nuova scansione'),
    editLabel: t('Modifica scansione'),
    intro: t('Quali indirizzi interrogare, con quali profili e ogni quanto. Quello che trova finisce in "Da approvare".'),
    label: (o) => o.name,
    detail: (o) => `/discovery-jobs/${o.id}`,
    filters: [{ name: 'site_id', label: t('Sede'), ref: 'sites' }],
    columns: [
      { name: 'name', label: t('Nome'), render: (o) => <strong>{o.name}</strong> },
      { name: 'targets', label: t('Indirizzi'), render: (o) => <Mono>{o.targets.join(', ')}</Mono> },
      { name: 'site_id', label: t('Sede dei device nuovi'), type: 'ref', ref: 'sites' },
      {
        name: 'interval_hours',
        label: t('Quando'),
        render: (o) => (!o.enabled ? <span className="muted">{t('Disattivata')}</span> : o.interval_hours ? t('Ogni {n} ore', { n: o.interval_hours }) : t('Solo a mano')),
      },
    ],
    fields: [
      { name: 'name', label: t('Nome'), required: true, placeholder: t('Switch sede di Torino') },
      { name: 'site_id', label: t('Sede dei device nuovi'), type: 'ref', ref: 'sites', required: true },
      {
        name: 'targets',
        label: t('Indirizzi da scansionare'),
        type: 'lines',
        required: true,
        placeholder: t('10.10.99.0/24\n10.10.98.1-20\n10.10.1.1'),
        help: t('Uno per riga: subnet, intervallo o IP singolo. Massimo 4096 indirizzi.'),
      },
      {
        name: 'profile_ids',
        label: t('Profili SNMP da provare'),
        type: 'refmulti',
        ref: 'snmp-profiles',
        ordered: true,
        required: true,
        help: t('Vengono provati nell\'ordine in cui li selezioni: vince il primo che risponde.'),
      },
      { name: 'interval_hours', label: t('Ripeti ogni (ore)'), type: 'number', placeholder: t('Vuoto = solo a mano') },
      { name: 'enabled', label: t('Attiva'), type: 'bool', default: true },
      { name: 'auto_new_interfaces', label: t('Aggiungi da sola le porte nuove dei device già censiti'), type: 'bool' },
      { name: 'auto_new_ips', label: t('Aggiungi da sola gli IP nuovi sulle porte già censite'), type: 'bool', help: t('Device nuovi, cavi e modifiche ai dati inseriti a mano restano sempre da approvare.') },
      description,
    ],
  },
})

const ALERT_TYPES = [
  { value: 'email', label: t('Email') },
  { value: 'webhook', label: t('Webhook (Teams, Slack…)') },
  { value: 'telegram', label: t('Telegram') },
]
const isType = (type) => (v) => v.type === type

// Switch di uno stack: si gestiscono dalla scheda del device dello stack (niente voce nel menu)
resources['stack-members'] = {
  path: 'stack-members',
  title: t('Membri degli stack'),
  newLabel: t('Nuovo membro dello stack'),
  editLabel: t('Modifica membro dello stack'),
  label: (o) => t('{device} membro {n}', { device: o.device_name, n: o.number }),
  filters: [{ name: 'device_id', label: t('Device'), ref: 'devices' }],
  columns: [
    { name: 'device_id', label: t('Stack'), render: (o) => <CellLink to={`/devices/${o.device_id}`}>{o.device_name}</CellLink> },
    { name: 'number', label: t('Membro') },
    { name: 'model', label: t('Modello') },
    { name: 'serial', label: t('Numero di serie'), type: 'mono' },
  ],
  fields: [
    { name: 'device_id', label: t('Device dello stack'), type: 'ref', ref: 'devices', required: true, createOnly: true },
    { name: 'number', label: t('Numero del membro'), type: 'number', required: true, help: t('1 per le porte Gi1/0/x, 2 per Gi2/0/x…') },
    { name: 'model', label: t('Modello'), placeholder: t('C9300-48P') },
    { name: 'serial', label: t('Numero di serie') },
    { name: 'rack_position', label: t('Unità nel rack'), type: 'number', help: t("L'unità più bassa occupata, nel rack del device.") },
    description,
  ],
}

resources['alert-channels'] = {
  path: 'alert-channels',
  title: t('Avvisi'),
  newLabel: t('Nuovo canale di avviso'),
  editLabel: t('Modifica canale di avviso'),
  intro:
    t('Dove arrivano gli avvisi quando un device con IP di management smette di rispondere (e quando torna). Il ritardo evita avvisi per un singolo ping perso; più device giù insieme arrivano in un solo messaggio.'),
  label: (o) => o.name,
  filters: [{ name: 'type', label: t('Tipo'), options: ALERT_TYPES }],
  columns: [
    { name: 'name', label: t('Nome'), render: (o) => <strong>{o.name}</strong> },
    { name: 'type', label: t('Tipo'), type: 'select', options: ALERT_TYPES },
    { name: 'enabled', label: t('Attivo'), type: 'bool' },
    { name: 'delay_minutes', label: t('Ritardo'), render: (o) => `${o.delay_minutes} min` },
    {
      name: 'last_sent_at',
      label: t('Ultimo invio'),
      render: (o) =>
        o.last_error ? (
          <span className="live live--down" title={tServer(o.last_error)}>{t('Errore: {error}', { error: tServer(o.last_error) })}</span>
        ) : (
          O.formatDateTime(o.last_sent_at)
        ),
    },
    { name: 'test', label: t('Prova'), render: (o) => <AlertTestButton channel={o} /> },
  ],
  fields: [
    { name: 'name', label: t('Nome'), required: true, placeholder: t('Teams reparto IT') },
    { name: 'type', label: t('Tipo'), type: 'select', options: ALERT_TYPES, default: 'webhook', required: true, createOnly: true },
    { name: 'delay_minutes', label: t('Ritardo (minuti)'), type: 'number', default: 5, help: t('Avvisa solo se il device non risponde da almeno questi minuti.') },
    { name: 'enabled', label: t('Attivo'), type: 'bool', default: true },
    { name: 'notify_recovery', label: t('Avvisa anche quando torna a rispondere'), type: 'bool', default: true },
    { name: 'language', label: t('Lingua dei messaggi'), type: 'select', options: LANGUAGES, default: 'it', required: true },
    // Webhook
    {
      name: 'webhook_url', label: t('Indirizzo del webhook'), type: 'secret', showIf: isType('webhook'),
      savedHint: (item) => (item?.has_secret ? t('Salvato: lascia vuoto per non cambiarlo') : 'https://…'),
      help: t('In Teams: canale → Workflows → "Invia avvisi webhook a un canale", poi copia l\'indirizzo.'),
    },
    {
      name: 'webhook_format', label: t('Formato'), type: 'select', showIf: isType('webhook'), default: 'text',
      options: [
        { value: 'text', label: t('Testo (Slack, Mattermost, Google Chat, vecchio connettore Teams)') },
        { value: 'teams', label: t('Teams Workflows (scheda adattiva)') },
      ],
    },
    // Telegram
    {
      name: 'telegram_token', label: t('Token del bot'), type: 'secret', showIf: isType('telegram'),
      savedHint: (item) => (item?.has_secret ? t('Salvato: lascia vuoto per non cambiarlo') : t('123456:ABC…')),
      help: t('Da @BotFather. Aggiungi il bot al gruppo che deve ricevere gli avvisi.'),
    },
    { name: 'telegram_chat_id', label: t('Chat'), showIf: isType('telegram'), placeholder: '-1001234567890', help: t('Id del gruppo o della chat.') },
    // Email
    { name: 'email_to', label: t('Destinatari'), type: 'lines', showIf: isType('email'), placeholder: t('it@azienda.it'), help: t('Uno per riga.') },
    { name: 'smtp_host', label: t('Server SMTP'), showIf: isType('email'), placeholder: t('smtp.azienda.it') },
    { name: 'smtp_port', label: t('Porta'), type: 'number', showIf: isType('email'), placeholder: '587' },
    {
      name: 'smtp_security', label: t('Sicurezza'), type: 'select', showIf: isType('email'), default: 'starttls',
      options: [{ value: 'starttls', label: t('STARTTLS (587)') }, { value: 'ssl', label: t('SSL/TLS (465)') }, { value: 'none', label: t('Nessuna (25)') }],
    },
    { name: 'smtp_user', label: t('Utente SMTP'), showIf: isType('email') },
    {
      name: 'smtp_password', label: t('Password SMTP'), type: 'secret', showIf: isType('email'),
      savedHint: (item) => (item?.has_secret ? t('Salvata: lascia vuoto per non cambiarla') : undefined),
    },
    { name: 'smtp_from', label: t('Mittente'), showIf: isType('email'), placeholder: t('netmap@azienda.it') },
    description,
  ],
}

resources.users = {
  path: 'users',
  title: t('Utenti'),
  newLabel: t('Nuovo utente'),
  editLabel: t('Modifica utente'),
  intro: t('Chi può accedere. Solo lettura: consulta e cerca. Modifica: cambia i dati e approva le scansioni. Amministratore: anche gli utenti.'),
  label: (o) => o.username,
  filters: [{ name: 'role', label: t('Ruolo'), options: ROLES }],
  columns: [
    { name: 'username', label: t('Nome utente'), render: (o) => <strong>{o.username}</strong> },
    { name: 'full_name', label: t('Nome') },
    { name: 'role', label: t('Ruolo'), type: 'select', options: ROLES },
    { name: 'active', label: t('Attivo'), type: 'bool' },
    { name: 'last_login_at', label: t('Ultimo accesso'), render: (o) => O.formatDateTime(o.last_login_at) },
  ],
  fields: [
    { name: 'username', label: t('Nome utente'), required: true, placeholder: t('mario.rossi') },
    { name: 'full_name', label: t('Nome e cognome') },
    { name: 'role', label: t('Ruolo'), type: 'select', options: ROLES, default: 'viewer', required: true },
    {
      name: 'password',
      label: t('Password'),
      type: 'secret',
      requiredOnCreate: true,
      savedHint: (item) => (item ? t('Lascia vuoto per non cambiarla') : undefined),
      help: t('Almeno 8 caratteri. Cambiandola, le sessioni aperte dell\'utente si chiudono.'),
    },
    { name: 'active', label: t('Attivo'), type: 'bool', default: true, help: t('Un utente disattivato non può più accedere.') },
  ],
}

/** Voci del menu: chiave di una risorsa oppure pagina speciale { to, title, badge }; admin: solo amministratori */
export const NAV = [
  { title: t('Rete'), items: ['maps', 'devices', { to: 'where', title: t("Dov'è collegato?") }, 'interfaces', 'cables'] },
  { title: t('Luoghi'), items: ['sites', 'locations', 'racks'] },
  { title: t('Indirizzamento'), items: ['prefixes', 'ip-addresses', 'vlans', 'vrfs'] },
  { title: t('Catalogo'), items: ['device-roles', 'device-types', 'manufacturers'] },
  {
    title: t('Scansione SNMP'),
    items: [{ to: 'discovery/changes', title: t('Da approvare'), badge: 'pending' }, 'discovery-jobs', 'snmp-profiles'],
  },
  { title: t('Attività'), items: [{ to: 'whats-changed', title: t('Cosa è cambiato') }, { to: 'history', title: t('Storico modifiche') }] },
  { title: t('Amministrazione'), admin: true, items: ['users', 'alert-channels', { to: 'updates', title: t('Aggiornamenti') }, { to: 'backup', title: t('Backup') }] },
]
