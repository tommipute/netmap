import { useState } from 'react'
import { IconButton } from './Icon'
import { t } from '../i18n'

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
          <input className="input" placeholder={t('Nome campo')} value={row.k} onChange={(e) => edit(i, 'k', e.target.value)} aria-label={t('Nome campo')} />
          <input className="input" placeholder={t('Valore')} value={row.v} onChange={(e) => edit(i, 'v', e.target.value)} aria-label={t('Valore')} />
          <IconButton icon="close" label={t('Rimuovi campo')} small className="btn--ghost" onClick={() => update(rows.filter((_, j) => j !== i))} />
        </div>
      ))}
      <IconButton icon="plus" label={t('Aggiungi campo')} small className="btn--ghost" onClick={() => update([...rows, { k: '', v: '' }])} />
    </div>
  )
}
