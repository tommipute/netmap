import { Link } from 'react-router-dom'
import { useAuth } from '../auth'
import { formatDateTime, formatSince, labelOf, SOURCES } from '../options'
import { Icon } from './Icon'
import { LOCALE, t } from '../i18n'

const TONE = {
  active: 'ok',
  connected: 'ok',
  planned: 'warn',
  reserved: 'warn',
  dhcp: 'info',
  offline: 'danger',
  decommissioned: 'muted',
  decommissioning: 'danger',
  deprecated: 'muted',
}

export function Badge({ value, options }) {
  if (!value) return <span className="muted">—</span>
  return <span className={`badge badge--${TONE[value] || 'muted'}`}>{labelOf(options, value)}</span>
}

/** Link dentro una riga cliccabile: non fa scattare anche il click della riga. */
export function CellLink({ to, children }) {
  return (
    <Link to={to} onClick={(e) => e.stopPropagation()}>
      {children}
    </Link>
  )
}

/** Icona dell'origine (a mano, scansione, import da un altro programma); il nome nel tooltip */
export function SourceIcon({ source, withLabel = false }) {
  const option = SOURCES.find((o) => o.value === source) || { label: source, icon: 'plug' }
  return (
    <span className={`source-icon source-icon--${source === 'manual' || source === 'snmp' ? source : 'import'}`} title={option.label}>
      <Icon name={option.icon} size={14} />
      {withLabel ? <span>{option.label}</span> : <span className="sr-only">{option.label}</span>}
    </span>
  )
}

export function Mono({ children }) {
  if (children === null || children === undefined || children === '') return <span className="muted">—</span>
  return <span className="mono">{children}</span>
}

export function ErrorBox({ error }) {
  if (!error) return null
  return (
    <p className="error-box" role="alert">
      {error.message || String(error)}
    </p>
  )
}

export function Loading() {
  return <p className="muted">{t('Caricamento…')}</p>
}

/** Stato live di un device: pallino + testo. Vuoto se il monitor non l'ha mai controllato. */
export function LiveStatus({ device, long = false }) {
  if (device.reachable === null || device.reachable === undefined) return <span className="muted">—</span>
  const up = device.reachable
  const title = t('Ultimo controllo: {when}', { when: formatDateTime(device.last_check_at) })
  return (
    <span className={`live${up ? '' : ' live--down'}`} title={title}>
      <span className={`live-dot live-dot--${up ? 'up' : 'down'}`} />
      {up ? t('Risponde') : t('Non risponde')}
      {long && device.reachable_changed_at && <span className="muted"> {formatSince(device.reachable_changed_at)}</span>}
      {long && up && device.rtt_ms !== null && device.rtt_ms !== undefined && <span className="muted"> · {device.rtt_ms} ms</span>}
    </span>
  )
}

/** Riga che compare solo sul foglio stampato: quando e chi ha stampato. */
export function PrintFooter() {
  const { user } = useAuth()
  const when = new Date().toLocaleString(LOCALE, { dateStyle: 'short', timeStyle: 'short' })
  return (
    <p className="print-only print-footer">
      {user ? t('Stampato da NetMap il {when} da {user}', { when, user: user.full_name || user.username }) : t('Stampato da NetMap il {when}', { when })}
    </p>
  )
}
