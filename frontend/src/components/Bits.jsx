import { Link } from 'react-router-dom'
import { labelOf } from '../options'

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
