import { LOCALE, t, tc } from './i18n'
import { getPref } from './prefs'

export const DEVICE_STATUS = [
  { value: 'active', label: t('Attivo') },
  { value: 'planned', label: t('Pianificato') },
  { value: 'offline', label: t('Offline') },
  { value: 'decommissioned', label: t('Dismesso') },
]

export const INTERFACE_TYPES = [
  { value: 'copper', label: t('Rame') },
  { value: 'fiber', label: t('Fibra') },
  { value: 'wireless', label: t('Wireless') },
  { value: 'virtual', label: t('Virtuale (SVI, loopback)') },
  { value: 'lag', label: t('LAG (port-channel)') },
  { value: 'other', label: t('Altro') },
]

export const INTERFACE_MODES = [
  { value: 'access', label: t('Access') },
  { value: 'trunk', label: t('Trunk') },
]

export const CABLE_TYPES = [
  { value: 'cat5e', label: t('Cat5e') },
  { value: 'cat6', label: t('Cat6') },
  { value: 'cat6a', label: t('Cat6a') },
  { value: 'fiber_mm', label: t('Fibra multimodale') },
  { value: 'fiber_sm', label: t('Fibra monomodale') },
  { value: 'dac', label: t('DAC') },
  { value: 'other', label: t('Altro') },
]

export const CABLE_STATUS = [
  { value: 'connected', label: t('Collegato') },
  { value: 'planned', label: t('Pianificato') },
  { value: 'decommissioning', label: t('Da dismettere') },
]

export const IPAM_STATUS = [
  { value: 'active', label: t('Attivo') },
  { value: 'reserved', label: t('Riservato') },
  { value: 'deprecated', label: t('Deprecato') },
]

export const IP_STATUS = [
  { value: 'active', label: t('Attivo') },
  { value: 'reserved', label: t('Riservato') },
  { value: 'dhcp', label: t('DHCP') },
  { value: 'deprecated', label: t('Deprecato') },
]

export const LENGTH_UNITS = [
  { value: 'm', label: t('metri') },
  { value: 'cm', label: t('centimetri') },
  { value: 'ft', label: t('piedi') },
]

// Origine dei dati, con l'icona che la mostra negli elenchi (SourceIcon): gli import da altri programmi hanno
// un valore per programma e la stessa icona
export const SOURCES = [
  { value: 'manual', label: t('Inserito a mano'), icon: 'user' },
  { value: 'snmp', label: t('Scansione SNMP'), icon: 'radar' },
  { value: 'netbox', label: t('Import da NetBox'), icon: 'plug' },
  { value: 'zabbix', label: t('Import da Zabbix'), icon: 'plug' },
  { value: 'librenms', label: t('Import da LibreNMS'), icon: 'plug' },
  { value: 'observium', label: t('Import da Observium'), icon: 'plug' },
  { value: 'prtg', label: t('Import da PRTG'), icon: 'plug' },
  { value: 'glpi', label: t('Import da GLPI'), icon: 'plug' },
  { value: 'lansweeper', label: t('Import da Lansweeper'), icon: 'plug' },
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
  { value: 'v1', label: t('SNMP v1 (community, apparati vecchi)') },
  { value: 'v2c', label: t('SNMP v2c (community)') },
  { value: 'v3', label: t('SNMPv3 (utente e chiavi)') },
]

export const SNMP_AUTH = [
  { value: 'sha', label: t('SHA') },
  { value: 'sha256', label: t('SHA-256') },
  { value: 'sha512', label: t('SHA-512') },
  { value: 'md5', label: t('MD5 (vecchio)') },
]

export const SNMP_PRIV = [
  { value: 'aes', label: t('AES-128') },
  { value: 'aes256', label: t('AES-256') },
  { value: 'des', label: t('DES (vecchio)') },
]

export const RUN_STATUS = [
  { value: 'queued', label: t('In coda') },
  { value: 'running', label: t('In corso') },
  { value: 'done', label: t('Completata') },
  { value: 'failed', label: t('Non riuscita') },
]

export const CHANGE_STATUS = [
  { value: 'pending', label: t('Da approvare') },
  { value: 'applied', label: t('Applicate') },
  { value: 'rejected', label: t('Rifiutate') },
  { value: 'failed', label: t('Non riuscite') },
]

export const CHANGE_ACTIONS = {
  create: { label: t('Nuovo'), tone: 'ok' },
  update: { label: tc('azione', 'Modifica'), tone: 'info' },
  stale: { label: t('Non più visto'), tone: 'warn' },
}

/** "2026-10-05T20:31:52Z" -> "05/10/26, 22:31" */
const RELATIVE_UNITS = [[60, 'second'], [3600, 'minute'], [86400, 'hour'], [7 * 86400, 'day']]

/**
 * Data e ora come scelto nelle preferenze: ora a 24 o 12 ore; "relative" = "3 ore fa" nell'ultima settimana.
 * exact: sempre la data completa (es. la data di stampa).
 */
export function formatDateTime(value, { exact = false } = {}) {
  if (!value) return '—'
  const date = new Date(value)
  if (!exact && getPref('dates') === 'relative') {
    const seconds = (date.getTime() - Date.now()) / 1000
    const found = RELATIVE_UNITS.findIndex(([limit]) => Math.abs(seconds) < limit)
    if (found >= 0) {
      const rtf = new Intl.RelativeTimeFormat(LOCALE, { numeric: 'auto' })
      if (found === 0) return rtf.format(0, 'second')
      return rtf.format(Math.round(seconds / RELATIVE_UNITS[found - 1][0]), RELATIVE_UNITS[found][1])
    }
  }
  return date.toLocaleString(LOCALE, { dateStyle: 'short', timeStyle: 'short', hour12: getPref('clock') === '12' })
}

/** Durata tra due date: "45 s", "3 min" */
export function formatDuration(start, end) {
  if (!start || !end) return '—'
  const seconds = Math.max(0, Math.round((new Date(end) - new Date(start)) / 1000))
  return seconds < 90 ? `${seconds} s` : `${Math.round(seconds / 60)} min`
}

// ---------- Stato live (fase 4) ----------
export const REACHABLE = [
  { value: 'true', label: t('Risponde') },
  { value: 'false', label: t('Non risponde') },
]

/** "da 5 min", "da 3 ore", "da 2 giorni" */
export function formatSince(value) {
  if (!value) return ''
  const minutes = Math.max(0, Math.round((Date.now() - new Date(value)) / 60000))
  if (minutes < 1) return t('da meno di un minuto')
  if (minutes < 90) return t('da {n} min', { n: minutes })
  const hours = Math.round(minutes / 60)
  if (hours < 36) return t('da {n} ore', { n: hours })
  return t('da {n} giorni', { n: Math.round(hours / 24) })
}
