import { useEffect, useRef, useState } from 'react'
import { api, qs } from '../api'
import { useApi, useDebounced, useOptions } from '../hooks'
import { resources } from '../resources'
import { RefSelect } from './RefSelect'
import RefLabel from './RefLabel'
import { t } from '../i18n'

// Campi del modulo di un canale di avviso: device e porte scelti, modelli dei messaggi con anteprima.

/** Pastiglie degli elementi scelti, con la × per toglierli. */
function Picked({ resource, value, onChange }) {
  if (!value.length) return null
  return (
    <div className="chips">
      {value.map((itemId) => (
        <span key={itemId} className="chip chip--value">
          <RefLabel resource={resource} id={itemId} />
          <button type="button" className="chip__remove" onClick={() => onChange(value.filter((v) => v !== itemId))}
            aria-label={t('Togli')}>
            ×
          </button>
        </span>
      ))}
    </div>
  )
}

/** Scelta di più elementi cercandoli sul server (funziona anche con migliaia di device). */
export function SearchMulti({ id, resource, value, onChange, params, label }) {
  const config = resources[resource]
  const selected = value || []
  const [text, setText] = useState('')
  const [open, setOpen] = useState(false)
  const q = useDebounced(text.trim())
  const boxRef = useRef(null)
  const results = useApi(open ? `/${config.path}${qs({ limit: 20, q, ...params })}` : null).data

  useEffect(() => {
    const close = (e) => boxRef.current && !boxRef.current.contains(e.target) && setOpen(false)
    document.addEventListener('mousedown', close)
    return () => document.removeEventListener('mousedown', close)
  }, [])

  const choices = (results?.items || []).filter((o) => !selected.includes(o.id))
  return (
    <>
      <Picked resource={resource} value={selected} onChange={onChange} />
      <div className="combo" ref={boxRef}>
        <input id={id} className="input" role="combobox" aria-expanded={open} aria-label={label} value={text}
          placeholder={t('Scrivi per cercare e aggiungere…')} onFocus={() => setOpen(true)}
          onChange={(e) => {
            setText(e.target.value)
            setOpen(true)
          }}
          onKeyDown={(e) => {
            if (e.key === 'Escape') setOpen(false)
            if (e.key === 'Enter') {
              e.preventDefault() // Invio sceglie il primo, non invia il modulo
              if (choices[0]) onChange([...selected, choices[0].id])
            }
          }} />
        {open && (
          <ul className="combo__list" role="listbox">
            {choices.map((o) => (
              <li key={o.id}>
                <button type="button" role="option" aria-selected="false" className="combo__item"
                  onClick={() => onChange([...selected, o.id])}>
                  {config.label(o)}
                </button>
              </li>
            ))}
            {results && !choices.length && <li className="combo__more hint">{t('Nessun risultato')}</li>}
            {results && results.total > results.items.length && (
              <li className="combo__more hint">{t('Altri {n}: scrivi di più per restringere', { n: results.total - results.items.length })}</li>
            )}
          </ul>
        )}
      </div>
    </>
  )
}

export const DeviceMulti = ({ id, value, onChange, field }) => (
  <SearchMulti id={id} resource="devices" value={value} onChange={onChange} label={field.label} />
)

/** Porte da seguire: si sceglie un device, poi si accendono le sue porte. */
export function PortPicker({ id, value, onChange }) {
  const selected = value || []
  const [deviceId, setDeviceId] = useState('')
  const ports = useOptions(deviceId ? 'interfaces' : null, { device_id: deviceId })
  const toggle = (portId) => onChange(selected.includes(portId) ? selected.filter((v) => v !== portId) : [...selected, portId])
  return (
    <>
      <Picked resource="interfaces" value={selected} onChange={onChange} />
      <RefSelect id={id} resource="devices" value={deviceId} onChange={setDeviceId} emptyLabel={t('Scegli il device…')}
        ariaLabel={t('Device delle porte')} />
      {deviceId !== '' && (
        ports.length ? (
          <div className="chips" role="group">
            {ports.map((o) => {
              const on = selected.includes(o.id)
              return (
                <button type="button" key={o.id} className={`chip${on ? ' chip--on' : ''}`} aria-pressed={on} onClick={() => toggle(o.id)}>
                  {o.name}
                </button>
              )
            })}
          </div>
        ) : (
          <p className="hint">{t('Questo device non ha porte.')}</p>
        )
      )}
    </>
  )
}

const KINDS = [
  { key: 'down', label: () => t('Device giù') },
  { key: 'up', label: () => t('Device tornato') },
  { key: 'port_down', label: () => t('Porta giù'), ports: true },
  { key: 'port_up', label: () => t('Porta tornata'), ports: true },
]
const PLACEHOLDERS = {
  it: ['{device}', '{ip}', '{sede}', '{posizione}', '{ruolo}', '{durata}', '{porta}', '{collegata}', '{descrizione}'],
  en: ['{device}', '{ip}', '{site}', '{location}', '{role}', '{time}', '{port}', '{remote}', '{description}'],
}

/** Modelli dei messaggi: vuoto = testo predefinito (mostrato in grigio); sotto, l'anteprima con dati di esempio. */
export function AlertTemplates({ value, onChange, values }) {
  const templates = value || {}
  const language = values.language || 'it'
  const ports = values.ports || 'none'
  const [preview, setPreview] = useState(null)
  const request = useDebounced(JSON.stringify({ language, ports, templates }), 400)

  useEffect(() => {
    let current = true
    api.post('/alert-messages/preview', JSON.parse(request))
      .then((data) => current && setPreview(data))
      .catch(() => current && setPreview(null))
    return () => {
      current = false
    }
  }, [request])

  const set = (key, text) => onChange({ ...templates, [key]: text })
  return (
    <div className="alert-templates">
      <p className="hint">
        {t('Lascia vuoto per il testo predefinito. Segnaposto:')}{' '}
        {PLACEHOLDERS[language].map((p) => <code key={p} className="alert-templates__tag">{p}</code>)}
        {' '}{t('Le parti tra parentesi o dopo · e › spariscono se il dato manca.')}
      </p>
      {KINDS.filter((k) => !k.ports || ports !== 'none').map((k) => (
        <label key={k.key} className="alert-templates__row">
          <span className="field__label">{k.label()}</span>
          <input className="input mono" value={templates[k.key] || ''} maxLength={500}
            placeholder={preview?.defaults?.[k.key] || ''} onChange={(e) => set(k.key, e.target.value)} />
        </label>
      ))}
      {preview?.unknown?.length > 0 && (
        <span className="hint hint--error">{t('Segnaposto sconosciuti (restano scritti così): {list}', { list: preview.unknown.map((n) => `{${n}}`).join(' ') })}</span>
      )}
      {preview && (
        <div className="alert-preview">
          <span className="field__label">{t('Anteprima (dati di esempio)')}</span>
          {['down', 'up'].map((kind) => (
            <div key={kind} className="alert-preview__message">
              <strong>{preview[kind].subject}</strong>
              <pre>{preview[kind].text}</pre>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
