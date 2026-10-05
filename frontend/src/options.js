export const DEVICE_STATUS = [
  { value: 'active', label: 'Attivo' },
  { value: 'planned', label: 'Pianificato' },
  { value: 'offline', label: 'Offline' },
  { value: 'decommissioned', label: 'Dismesso' },
]

export const INTERFACE_TYPES = [
  { value: 'copper', label: 'Rame' },
  { value: 'fiber', label: 'Fibra' },
  { value: 'wireless', label: 'Wireless' },
  { value: 'virtual', label: 'Virtuale (SVI, loopback)' },
  { value: 'lag', label: 'LAG (port-channel)' },
  { value: 'other', label: 'Altro' },
]

export const INTERFACE_MODES = [
  { value: 'access', label: 'Access' },
  { value: 'trunk', label: 'Trunk' },
]

export const CABLE_TYPES = [
  { value: 'cat5e', label: 'Cat5e' },
  { value: 'cat6', label: 'Cat6' },
  { value: 'cat6a', label: 'Cat6a' },
  { value: 'fiber_mm', label: 'Fibra multimodale' },
  { value: 'fiber_sm', label: 'Fibra monomodale' },
  { value: 'dac', label: 'DAC' },
  { value: 'other', label: 'Altro' },
]

export const CABLE_STATUS = [
  { value: 'connected', label: 'Collegato' },
  { value: 'planned', label: 'Pianificato' },
  { value: 'decommissioning', label: 'Da dismettere' },
]

export const IPAM_STATUS = [
  { value: 'active', label: 'Attivo' },
  { value: 'reserved', label: 'Riservato' },
  { value: 'deprecated', label: 'Deprecato' },
]

export const IP_STATUS = [
  { value: 'active', label: 'Attivo' },
  { value: 'reserved', label: 'Riservato' },
  { value: 'dhcp', label: 'DHCP' },
  { value: 'deprecated', label: 'Deprecato' },
]

export const LENGTH_UNITS = [
  { value: 'm', label: 'metri' },
  { value: 'cm', label: 'centimetri' },
  { value: 'ft', label: 'piedi' },
]

export const SOURCES = [
  { value: 'manual', label: 'Inserito a mano' },
  { value: 'snmp', label: 'Scansione SNMP' },
]

const ALL = [...DEVICE_STATUS, ...CABLE_STATUS, ...IP_STATUS]

export function labelOf(options, value) {
  if (value === null || value === undefined || value === '') return '—'
  return (options || ALL).find((o) => o.value === value)?.label ?? value
}

/** 1000 -> "1 G", 100 -> "100 M" */
export function formatSpeed(mbps) {
  if (!mbps) return '—'
  return mbps >= 1000 ? `${mbps / 1000} G` : `${mbps} M`
}
