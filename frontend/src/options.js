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

// ---------- Scansione SNMP ----------
export const SNMP_VERSIONS = [
  { value: 'v2c', label: 'SNMP v2c (community)' },
  { value: 'v3', label: 'SNMPv3 (utente e chiavi)' },
]

export const SNMP_AUTH = [
  { value: 'sha', label: 'SHA' },
  { value: 'sha256', label: 'SHA-256' },
  { value: 'sha512', label: 'SHA-512' },
  { value: 'md5', label: 'MD5 (vecchio)' },
]

export const SNMP_PRIV = [
  { value: 'aes', label: 'AES-128' },
  { value: 'aes256', label: 'AES-256' },
  { value: 'des', label: 'DES (vecchio)' },
]

export const RUN_STATUS = [
  { value: 'queued', label: 'In coda' },
  { value: 'running', label: 'In corso' },
  { value: 'done', label: 'Completata' },
  { value: 'failed', label: 'Non riuscita' },
]

export const CHANGE_STATUS = [
  { value: 'pending', label: 'Da approvare' },
  { value: 'applied', label: 'Applicate' },
  { value: 'rejected', label: 'Rifiutate' },
  { value: 'failed', label: 'Non riuscite' },
]

export const CHANGE_ACTIONS = {
  create: { label: 'Nuovo', tone: 'ok' },
  update: { label: 'Modifica', tone: 'info' },
  stale: { label: 'Non più visto', tone: 'warn' },
}

/** "2026-10-05T20:31:52Z" -> "05/10/26, 22:31" */
export function formatDateTime(value) {
  if (!value) return '—'
  return new Date(value).toLocaleString('it-IT', { dateStyle: 'short', timeStyle: 'short' })
}

/** Durata tra due date: "45 s", "3 min" */
export function formatDuration(start, end) {
  if (!start || !end) return '—'
  const seconds = Math.max(0, Math.round((new Date(end) - new Date(start)) / 1000))
  return seconds < 90 ? `${seconds} s` : `${Math.round(seconds / 60)} min`
}

// ---------- Stato live (fase 4) ----------
export const REACHABLE = [
  { value: 'true', label: 'Risponde' },
  { value: 'false', label: 'Non risponde' },
]

/** "da 5 min", "da 3 ore", "da 2 giorni" */
export function formatSince(value) {
  if (!value) return ''
  const minutes = Math.max(0, Math.round((Date.now() - new Date(value)) / 60000))
  if (minutes < 1) return 'da meno di un minuto'
  if (minutes < 90) return `da ${minutes} min`
  const hours = Math.round(minutes / 60)
  if (hours < 36) return `da ${hours} ore`
  return `da ${Math.round(hours / 24)} giorni`
}
