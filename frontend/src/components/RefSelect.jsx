import { useEffect, useRef, useState } from 'react'
import { qs } from '../api'
import { useApi, useDebounced, useOptions, useOptionsPage } from '../hooks'
import { resources } from '../resources'

/** Oltre i 1000 elementi: campo di ricerca che interroga il server (es. migliaia di device o interfacce). */
function SearchSelect({ id, config, value, onChange, params, disabled, emptyLabel, ariaLabel }) {
  const [text, setText] = useState('')
  const [open, setOpen] = useState(false)
  const q = useDebounced(text.trim())
  const boxRef = useRef(null)
  const current = useApi(value ? `/${config.path}/${value}` : null).data
  const results = useApi(open ? `/${config.path}${qs({ limit: 20, q, ...params })}` : null).data

  useEffect(() => {
    const close = (e) => boxRef.current && !boxRef.current.contains(e.target) && setOpen(false)
    document.addEventListener('mousedown', close)
    return () => document.removeEventListener('mousedown', close)
  }, [])

  const choose = (item) => {
    onChange(item ? item.id : '')
    setText('')
    setOpen(false)
  }

  return (
    <div className="combo" ref={boxRef}>
      <input
        id={id}
        className="input"
        role="combobox"
        aria-expanded={open}
        aria-label={ariaLabel}
        disabled={disabled}
        placeholder={current ? config.label(current) : `${emptyLabel} (scrivi per cercare)`}
        value={text}
        onFocus={() => setOpen(true)}
        onChange={(e) => {
          setText(e.target.value)
          setOpen(true)
        }}
        onKeyDown={(e) => e.key === 'Escape' && setOpen(false)}
      />
      {open && (
        <ul className="combo__list" role="listbox">
          <li>
            <button type="button" className="combo__item muted" onClick={() => choose(null)}>{emptyLabel}</button>
          </li>
          {(results?.items || []).map((o) => (
            <li key={o.id}>
              <button type="button" role="option" aria-selected={o.id === value} className="combo__item" onClick={() => choose(o)}>
                {config.label(o)}
              </button>
            </li>
          ))}
          {results && results.total > results.items.length && (
            <li className="combo__more hint">Altri {results.total - results.items.length}: scrivi di più per restringere</li>
          )}
        </ul>
      )}
    </div>
  )
}

/** Menu a tendina con gli elementi di un'altra entità (sedi, ruoli, VLAN...). */
export function RefSelect({ id, resource, value, onChange, params, disabled, emptyLabel = '—', waitLabel, ariaLabel }) {
  const config = resources[resource]
  const { items, total } = useOptionsPage(waitLabel ? null : config.path, params)
  if (!waitLabel && total > items.length) {
    return (
      <SearchSelect id={id} config={config} value={value} onChange={onChange} params={params} disabled={disabled}
        emptyLabel={emptyLabel} ariaLabel={ariaLabel} />
    )
  }
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
