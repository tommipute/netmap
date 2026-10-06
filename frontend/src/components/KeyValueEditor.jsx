import { useState } from 'react'
import { Icon, IconButton } from './Icon'

/** Editor dei campi personalizzati: coppie nome / valore. */
export default function KeyValueEditor({ value, onChange }) {
  const [rows, setRows] = useState(() => Object.entries(value || {}).map(([k, v]) => ({ k, v: String(v ?? '') })))

  const update = (next) => {
    setRows(next)
    onChange(Object.fromEntries(next.filter((r) => r.k.trim()).map((r) => [r.k.trim(), r.v])))
  }
  const edit = (index, key, text) => update(rows.map((row, i) => (i === index ? { ...row, [key]: text } : row)))

  return (
    <div className="kv">
      {rows.map((row, i) => (
        <div className="kv__row" key={i}>
          <input className="input" placeholder="Nome campo" value={row.k} onChange={(e) => edit(i, 'k', e.target.value)} aria-label="Nome campo" />
          <input className="input" placeholder="Valore" value={row.v} onChange={(e) => edit(i, 'v', e.target.value)} aria-label="Valore" />
          <IconButton icon="close" label="Rimuovi campo" small className="btn--ghost" onClick={() => update(rows.filter((_, j) => j !== i))} />
        </div>
      ))}
      <button type="button" className="btn btn--ghost btn--sm" onClick={() => update([...rows, { k: '', v: '' }])}>
        <Icon name="plus" />
        Aggiungi campo
      </button>
    </div>
  )
}
