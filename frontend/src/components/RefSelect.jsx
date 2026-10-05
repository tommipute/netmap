import { useOptions } from '../hooks'
import { resources } from '../resources'

/** Menu a tendina con gli elementi di un'altra entità (sedi, ruoli, VLAN...). */
export function RefSelect({ id, resource, value, onChange, params, disabled, emptyLabel = '—', waitLabel, ariaLabel }) {
  const config = resources[resource]
  const items = useOptions(waitLabel ? null : config.path, params)
  return (
    <select
      id={id}
      className="input"
      value={value ?? ''}
      disabled={disabled || Boolean(waitLabel)}
      aria-label={ariaLabel}
      onChange={(e) => onChange(e.target.value === '' ? '' : Number(e.target.value))}
    >
      <option value="">{waitLabel || emptyLabel}</option>
      {items.map((o) => (
        <option key={o.id} value={o.id}>
          {config.label(o)}
        </option>
      ))}
    </select>
  )
}

/** Selezione multipla a "pastiglie" (es. VLAN tagged su un trunk). ordered: mostra l'ordine di scelta. */
export function RefMulti({ resource, value, onChange, ordered = false }) {
  const config = resources[resource]
  const items = useOptions(config.path)
  const selected = value || []
  if (items.length === 0) return <p className="hint">Nessuna voce disponibile: creane prima qualcuna.</p>
  const toggle = (itemId) =>
    onChange(selected.includes(itemId) ? selected.filter((v) => v !== itemId) : [...selected, itemId])
  return (
    <div className="chips" role="group">
      {items.map((o) => {
        const on = selected.includes(o.id)
        return (
          <button type="button" key={o.id} className={`chip${on ? ' chip--on' : ''}`} aria-pressed={on} onClick={() => toggle(o.id)}>
            {ordered && on && <span className="chip__order">{selected.indexOf(o.id) + 1}</span>}
            {config.label(o)}
          </button>
        )
      })}
    </div>
  )
}
