/**
 * Configurazione delle entità: colonne della tabella e campi del modulo.
 * Per aggiungere un'entità basta una voce qui (più il backend).
 */
import { ROLES } from './auth'
import { Badge, CellLink, LiveStatus, Mono } from './components/Bits'
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
    // Modifica in blocco dall'elenco (selezione multipla)
    bulkFields: ['status', 'site_id', 'location_id', 'rack_id', 'role_id', 'device_type_id'],
    filters: [
      { name: 'site_id', label: 'Sede', ref: 'sites' },
      { name: 'role_id', label: 'Ruolo', ref: 'device-roles' },
      { name: 'status', label: 'Stato', options: O.DEVICE_STATUS },
      { name: 'reachable', label: 'Stato live', options: O.REACHABLE },
    ],
    columns: [
      { name: 'name', label: 'Nome', render: (o) => <strong>{o.name}</strong> },
      { name: 'status', label: 'Stato', type: 'badge', options: O.DEVICE_STATUS },
      { name: 'reachable', label: 'Stato live', render: (o) => <LiveStatus device={o} /> },
      {
        name: 'management_ip',
        label: 'IP',
        render: (o) => (o.management_ip ? <Mono>{o.management_ip.split('/')[0]}</Mono> : <span className="muted">—</span>),
      },
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
      {
        name: 'management_ip',
        label: 'IP di management',
        placeholder: '10.10.99.55/24',
        help: "Quello per SSH, web e SNMP. Va sulla porta di management (se manca si crea \"mgmt\"). Vuoto: nessuno.",
      },
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
    detail: (o) => `/racks/${o.id}`,
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
        // Uno solo per device: se il device ne ha già un altro la casella è bloccata
        lockedBy: {
          url: (v) => (v.interface_id ? `/interfaces/${v.interface_id}` : null),
          reason: (iface, v, item) =>
            iface.device_management_ip && !(item?.is_primary && item.interface_id === Number(v.interface_id))
              ? `${iface.device_name} ha già l'IP di management ${iface.device_management_ip}: ce n'è uno solo per device. Per cambiarlo usa il campo nella scheda del device.`
              : null,
        },
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

const isV3 = (v) => v.version === 'v3'
const savedSecret = (flag) => (item) => (item?.[flag] ? 'Salvata: lascia vuoto per non cambiarla' : undefined)

Object.assign(resources, {
  'snmp-profiles': {
    path: 'snmp-profiles',
    title: 'Profili SNMP',
    newLabel: 'Nuovo profilo SNMP',
    editLabel: 'Modifica profilo SNMP',
    intro: 'Le credenziali con cui la scansione interroga i device. Community e chiavi sono salvate cifrate e non si possono rileggere.',
    label: (o) => o.name,
    columns: [
      { name: 'name', label: 'Nome', render: (o) => <strong>{o.name}</strong> },
      { name: 'version', label: 'Versione', type: 'select', options: O.SNMP_VERSIONS },
      {
        name: 'credentials',
        label: 'Credenziali',
        render: (o) =>
          o.version === 'v3' ? (
            <>
              <Mono>{o.username}</Mono>
              {o.auth_protocol && <span className="tag">{o.auth_protocol.toUpperCase()}</span>}
              {o.priv_protocol && <span className="tag">{o.priv_protocol.toUpperCase()}</span>}
            </>
          ) : o.has_community ? (
            'Community salvata'
          ) : (
            <span className="muted">Manca la community</span>
          ),
      },
      { name: 'port', label: 'Porta', type: 'mono' },
      { name: 'description', label: 'Note' },
    ],
    fields: [
      { name: 'name', label: 'Nome', required: true, placeholder: 'Switch sede, v2c' },
      { name: 'version', label: 'Versione', type: 'select', options: O.SNMP_VERSIONS, default: 'v2c', required: true },
      { name: 'community', label: 'Community', type: 'secret', showIf: (v) => !isV3(v), savedHint: savedSecret('has_community') },
      { name: 'username', label: 'Utente', showIf: isV3, hiddenValue: undefined },
      { name: 'auth_protocol', label: 'Autenticazione', type: 'select', options: O.SNMP_AUTH, emptyLabel: 'Nessuna', showIf: isV3, hiddenValue: undefined },
      { name: 'auth_key', label: 'Chiave di autenticazione', type: 'secret', showIf: (v) => isV3(v) && !!v.auth_protocol, savedHint: savedSecret('has_auth_key'), help: 'Almeno 8 caratteri.' },
      { name: 'priv_protocol', label: 'Cifratura', type: 'select', options: O.SNMP_PRIV, emptyLabel: 'Nessuna', showIf: (v) => isV3(v) && !!v.auth_protocol, hiddenValue: undefined },
      { name: 'priv_key', label: 'Chiave di cifratura', type: 'secret', showIf: (v) => isV3(v) && !!v.priv_protocol, savedHint: savedSecret('has_priv_key'), help: 'Almeno 8 caratteri.' },
      { name: 'context_name', label: 'Context name', showIf: isV3, hiddenValue: undefined, help: 'Quasi sempre vuoto.' },
      { name: 'port', label: 'Porta UDP', type: 'number', default: 161 },
      { name: 'timeout', label: 'Attesa per richiesta (secondi)', type: 'number', default: 2 },
      { name: 'retries', label: 'Tentativi in più', type: 'number', default: 1 },
      description,
    ],
  },

  'discovery-jobs': {
    path: 'discovery-jobs',
    title: 'Scansioni',
    newLabel: 'Nuova scansione',
    editLabel: 'Modifica scansione',
    intro: 'Quali indirizzi interrogare, con quali profili e ogni quanto. Quello che trova finisce in "Da approvare".',
    label: (o) => o.name,
    detail: (o) => `/discovery-jobs/${o.id}`,
    filters: [{ name: 'site_id', label: 'Sede', ref: 'sites' }],
    columns: [
      { name: 'name', label: 'Nome', render: (o) => <strong>{o.name}</strong> },
      { name: 'targets', label: 'Indirizzi', render: (o) => <Mono>{o.targets.join(', ')}</Mono> },
      { name: 'site_id', label: 'Sede dei device nuovi', type: 'ref', ref: 'sites' },
      {
        name: 'interval_hours',
        label: 'Quando',
        render: (o) => (!o.enabled ? <span className="muted">Disattivata</span> : o.interval_hours ? `Ogni ${o.interval_hours} ore` : 'Solo a mano'),
      },
    ],
    fields: [
      { name: 'name', label: 'Nome', required: true, placeholder: 'Switch sede di Torino' },
      { name: 'site_id', label: 'Sede dei device nuovi', type: 'ref', ref: 'sites', required: true },
      {
        name: 'targets',
        label: 'Indirizzi da scansionare',
        type: 'lines',
        required: true,
        placeholder: '10.10.99.0/24\n10.10.98.1-20\n10.10.1.1',
        help: 'Uno per riga: subnet, intervallo o IP singolo. Massimo 4096 indirizzi.',
      },
      {
        name: 'profile_ids',
        label: 'Profili SNMP da provare',
        type: 'refmulti',
        ref: 'snmp-profiles',
        ordered: true,
        required: true,
        help: 'Vengono provati nell\'ordine in cui li selezioni: vince il primo che risponde.',
      },
      { name: 'interval_hours', label: 'Ripeti ogni (ore)', type: 'number', placeholder: 'Vuoto = solo a mano' },
      { name: 'enabled', label: 'Attiva', type: 'bool', default: true },
      { name: 'auto_new_interfaces', label: 'Aggiungi da sola le porte nuove dei device già censiti', type: 'bool' },
      { name: 'auto_new_ips', label: 'Aggiungi da sola gli IP nuovi sulle porte già censite', type: 'bool', help: 'Device nuovi, cavi e modifiche ai dati inseriti a mano restano sempre da approvare.' },
      description,
    ],
  },
})

resources.users = {
  path: 'users',
  title: 'Utenti',
  newLabel: 'Nuovo utente',
  editLabel: 'Modifica utente',
  intro: 'Chi può accedere. Solo lettura: consulta e cerca. Modifica: cambia i dati e approva le scansioni. Amministratore: anche gli utenti.',
  label: (o) => o.username,
  filters: [{ name: 'role', label: 'Ruolo', options: ROLES }],
  columns: [
    { name: 'username', label: 'Nome utente', render: (o) => <strong>{o.username}</strong> },
    { name: 'full_name', label: 'Nome' },
    { name: 'role', label: 'Ruolo', type: 'select', options: ROLES },
    { name: 'active', label: 'Attivo', type: 'bool' },
    { name: 'last_login_at', label: 'Ultimo accesso', render: (o) => O.formatDateTime(o.last_login_at) },
  ],
  fields: [
    { name: 'username', label: 'Nome utente', required: true, placeholder: 'mario.rossi' },
    { name: 'full_name', label: 'Nome e cognome' },
    { name: 'role', label: 'Ruolo', type: 'select', options: ROLES, default: 'viewer', required: true },
    {
      name: 'password',
      label: 'Password',
      type: 'secret',
      requiredOnCreate: true,
      savedHint: (item) => (item ? 'Lascia vuoto per non cambiarla' : undefined),
      help: 'Almeno 8 caratteri. Cambiandola, le sessioni aperte dell\'utente si chiudono.',
    },
    { name: 'active', label: 'Attivo', type: 'bool', default: true, help: 'Un utente disattivato non può più accedere.' },
  ],
}

/** Voci del menu: chiave di una risorsa oppure pagina speciale { to, title, badge }; admin: solo amministratori */
export const NAV = [
  { title: 'Rete', items: ['maps', 'devices', { to: 'where', title: "Dov'è collegato?" }, 'interfaces', 'cables'] },
  { title: 'Luoghi', items: ['sites', 'locations', 'racks'] },
  { title: 'Indirizzamento', items: ['prefixes', 'ip-addresses', 'vlans', 'vrfs'] },
  { title: 'Catalogo', items: ['device-roles', 'device-types', 'manufacturers'] },
  {
    title: 'Scansione SNMP',
    items: [{ to: 'discovery/changes', title: 'Da approvare', badge: 'pending' }, 'discovery-jobs', 'snmp-profiles'],
  },
  { title: 'Attività', items: [{ to: 'history', title: 'Storico modifiche' }] },
  { title: 'Amministrazione', admin: true, items: ['users'] },
]
