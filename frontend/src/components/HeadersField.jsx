import { useState } from 'react'
import { IconButton } from './Icon'
import { t } from '../i18n'

/** Intestazioni HTTP in più di un webhook: nome / valore. I valori salvati non tornano dall'API (arrivano vuoti):
 * lasciati vuoti restano quelli salvati. Valore null = non toccate (nessuna modifica nel modulo). */
export default function HeadersField({ value, onChange }) {
  const [saved] = useState(() => new Set(Object.keys(value || {})))
  const [rows, setRows] = useState(() => Object.keys(value || {}).map((k) => ({ k, v: '' })))

  const update = (next) => {
    setRows(next)
    onChange(Object.fromEntries(next.filter((r) => r.k.trim()).map((r) => [r.k.trim(), r.v])))
  }
  const edit = (index, key, text) => update(rows.map((row, i) => (i === index ? { ...row, [key]: text } : row)))

  return (
    <div className="kv">
      {rows.map((row, i) => (
        <div className="kv__row" key={i}>
          <input className="input mono" placeholder="Authorization" value={row.k} onChange={(e) => edit(i, 'k', e.target.value)} aria-label={t('Nome dell\'intestazione')} />
          <input className="input mono" type="password" autoComplete="new-password" value={row.v}
            placeholder={saved.has(row.k.trim()) ? t('Salvato: lascia vuoto per non cambiarlo') : 'Bearer …'}
            onChange={(e) => edit(i, 'v', e.target.value)} aria-label={t('Valore')} />
          <IconButton icon="close" label={t('Togli l\'intestazione')} small className="btn--ghost" onClick={() => update(rows.filter((_, j) => j !== i))} />
        </div>
      ))}
      <IconButton icon="plus" label={t('Aggiungi un\'intestazione')} small className="btn--ghost" onClick={() => update([...rows, { k: '', v: '' }])} />
    </div>
  )
}
