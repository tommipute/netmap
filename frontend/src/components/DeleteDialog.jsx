import { useState } from 'react'
import { api, qs } from '../api'
import { invalidate } from '../hooks'
import { resources } from '../resources'
import Modal from './Modal'
import { t } from '../i18n'

/**
 * Conferma di eliminazione con le opzioni della risorsa (config.deleteOptions, es. per i device "elimina anche
 * gli IP"), per uno o più elementi. Le opzioni vanno all'API come parametri (?with_ips=true).
 */
export default function DeleteDialog({ resourceKey, items, note, onClose, onDone }) {
  const config = resources[resourceKey]
  const options = config.deleteOptions || []
  const [values, setValues] = useState(() => Object.fromEntries(options.map((o) => [o.name, o.default ?? false])))
  const [progress, setProgress] = useState(null)
  const one = items.length === 1

  const submit = async () => {
    const params = qs(Object.fromEntries(Object.entries(values).filter(([, on]) => on).map(([name]) => [name, 'true'])))
    const failed = []
    for (let i = 0; i < items.length; i++) {
      setProgress(i + 1)
      try {
        await api.del(`/${config.path}/${items[i].id}${params}`)
      } catch (err) {
        failed.push({ label: config.label(items[i]), error: err.message })
      }
    }
    invalidate()
    onDone({ done: items.length - failed.length, failed, verb: 'eliminati' })
  }

  return (
    <Modal title={one ? t('Eliminare {name}?', { name: config.label(items[0]) }) : t('Eliminare {n} elementi?', { n: items.length })} onClose={onClose}>
      <div className="form">
        {note && <p>{note}</p>}
        {!one && (
          <p className="hint">{items.slice(0, 8).map((item) => config.label(item)).join(', ')}{items.length > 8 ? ` ${t('e altri {n}', { n: items.length - 8 })}` : ''}</p>
        )}
        {options.map((o) => (
          <div key={o.name} className="field field--wide">
            <label className="check">
              <input type="checkbox" checked={values[o.name]} disabled={progress !== null}
                onChange={(e) => setValues((prev) => ({ ...prev, [o.name]: e.target.checked }))} />
              {o.label}
            </label>
            {o.help && <span className="hint">{o.help}</span>}
          </div>
        ))}
        <p className="hint">{t('Non si può annullare.')}</p>
        <div className="modal__footer">
          <button type="button" className="btn btn--ghost" onClick={onClose} disabled={progress !== null}>{t('Annulla')}</button>
          <button type="button" className="btn btn--primary btn--danger-fill" onClick={submit} disabled={progress !== null}>
            {progress !== null ? t('Elimino {i} di {n}…', { i: progress, n: items.length }) : t('Elimina')}
          </button>
        </div>
      </div>
    </Modal>
  )
}
