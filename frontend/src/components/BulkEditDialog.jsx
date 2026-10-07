import { useState } from 'react'
import { api } from '../api'
import { invalidate } from '../hooks'
import { resources } from '../resources'
import Modal from './Modal'
import { FieldControl, convert, emptyValue, isEmpty } from './ResourceForm'

/** Valore comune a tutti gli elementi scelti (undefined se diverso). */
function common(items, name) {
  const first = items[0]?.[name]
  return items.every((item) => item[name] === first) ? first : undefined
}

/**
 * Modifica in blocco: si spuntano i campi da cambiare e il nuovo valore vale per tutti gli elementi scelti.
 * Campi in config.bulkFields. Un campo che dipende da un altro (posizione/rack dalla sede) usa la sede nuova,
 * oppure quella comune agli elementi; se cambia la sede, posizione e rack non spuntati vengono svuotati.
 */
export default function BulkEditDialog({ resourceKey, items, onClose, onDone }) {
  const config = resources[resourceKey]
  const fields = config.fields.filter((f) => config.bulkFields.includes(f.name))
  const [enabled, setEnabled] = useState({})
  const [values, setValues] = useState(() =>
    Object.fromEntries(fields.map((f) => [f.name, common(items, f.name) ?? emptyValue(f)])),
  )
  const [progress, setProgress] = useState(null)
  const [error, setError] = useState(null)

  // Valore di riferimento di un campo: quello nuovo se spuntato, altrimenti quello comune a tutti
  const effective = (name) => (enabled[name] ? values[name] : common(items, name))
  // Anche i campi non modificabili in blocco (es. la sede di un rack): servono a filtrare quelli che ne dipendono
  const context = Object.fromEntries(config.fields.map((f) => [f.name, effective(f.name) ?? '']))

  const setValue = (name, value) =>
    setValues((prev) => {
      const next = { ...prev, [name]: value }
      for (const f of fields) if (f.dependsOn === name && prev[name] !== value) next[f.name] = emptyValue(f)
      return next
    })

  const toggle = (name, on) => setEnabled((prev) => ({ ...prev, [name]: on }))

  const submit = async (e) => {
    e.preventDefault()
    const payload = {}
    for (const f of fields) {
      if (!enabled[f.name]) continue
      if (f.required && isEmpty(values[f.name])) {
        setError(`Scegli un valore per "${f.label}".`)
        return
      }
      payload[f.name] = convert(f, values[f.name], true)
    }
    // Sede cambiata: posizione e rack non scelti si svuotano (sarebbero di un'altra sede)
    for (const f of fields) {
      if (f.dependsOn && enabled[f.dependsOn] && !enabled[f.name]) payload[f.name] = null
    }
    if (Object.keys(payload).length === 0) {
      setError('Spunta almeno un campo da cambiare.')
      return
    }
    setError(null)
    const failed = []
    for (let i = 0; i < items.length; i++) {
      setProgress(i + 1)
      try {
        await api.patch(`/${config.path}/${items[i].id}`, payload)
      } catch (err) {
        failed.push({ label: config.label(items[i]), error: err.message })
      }
    }
    invalidate()
    onDone({ done: items.length - failed.length, failed, verb: 'modificati' })
  }

  return (
    <Modal title={`Modifica ${items.length} elementi`} onClose={onClose}>
      <form className="form" onSubmit={submit} noValidate>
        <p className="hint">Spunta i campi da cambiare: il nuovo valore vale per tutti. Gli altri campi restano com'erano.</p>
        <div className="bulk-fields">
          {fields.map((f) => {
            const parent = f.dependsOn ? context[f.dependsOn] : null
            const waiting = f.dependsOn && isEmpty(parent)
            const parentEditable = fields.some((p) => p.name === f.dependsOn)
            const field = waiting ? { ...f, waitLabel: parentEditable ? 'Prima scegli la sede' : 'Sono di sedi diverse' } : f
            return (
              <div key={f.name} className={`bulk-field${enabled[f.name] ? ' bulk-field--on' : ''}`}>
                <label className="check">
                  <input type="checkbox" checked={Boolean(enabled[f.name])} onChange={(e) => toggle(f.name, e.target.checked)} />
                  {f.label}
                </label>
                <div onFocusCapture={() => !enabled[f.name] && toggle(f.name, true)}>
                  <FieldControl field={field} value={values[f.name]} values={context} fields={fields}
                    disabled={progress !== null} onChange={(v) => { toggle(f.name, true); setValue(f.name, v) }} />
                </div>
              </div>
            )
          })}
        </div>
        {error && <p className="form__error" role="alert">{error}</p>}
        <div className="modal__footer">
          <button type="button" className="btn btn--ghost" onClick={onClose} disabled={progress !== null}>Annulla</button>
          <button type="submit" className="btn btn--primary" disabled={progress !== null}>
            {progress !== null ? `Modifico ${progress} di ${items.length}…` : `Modifica ${items.length} elementi`}
          </button>
        </div>
      </form>
    </Modal>
  )
}
