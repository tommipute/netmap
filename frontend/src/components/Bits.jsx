import { Link } from 'react-router-dom'
import { useAuth } from '../auth'
import { formatDateTime, formatSince, labelOf } from '../options'

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
  return <p className="muted">Caricamento…</p>
}

/** Stato live di un device: pallino + testo. Vuoto se il monitor non l'ha mai controllato. */
export function LiveStatus({ device, long = false }) {
  if (device.reachable === null || device.reachable === undefined) return <span className="muted">—</span>
  const up = device.reachable
  const title = `Ultimo controllo: ${formatDateTime(device.last_check_at)}`
  return (
    <span className={`live${up ? '' : ' live--down'}`} title={title}>
      <span className={`live-dot live-dot--${up ? 'up' : 'down'}`} />
      {up ? 'Risponde' : 'Non risponde'}
      {long && device.reachable_changed_at && <span className="muted"> {formatSince(device.reachable_changed_at)}</span>}
      {long && up && device.rtt_ms !== null && device.rtt_ms !== undefined && <span className="muted"> · {device.rtt_ms} ms</span>}
    </span>
  )
}

/** Riga che compare solo sul foglio stampato: quando e chi ha stampato. */
export function PrintFooter() {
  const { user } = useAuth()
  const when = new Date().toLocaleString('it-IT', { dateStyle: 'short', timeStyle: 'short' })
  return (
    <p className="print-only print-footer">
      Stampato da NetMap il {when}{user ? ` da ${user.full_name || user.username}` : ''}
    </p>
  )
}
