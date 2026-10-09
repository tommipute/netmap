import { useEffect, useState } from 'react'
import { api } from '../api'
import ChipInput from './ChipInput'
import { invalidate, useApi } from '../hooks'
import { resources } from '../resources'
import InterfacePicker from './InterfacePicker'
import KeyValueEditor from './KeyValueEditor'
import Modal from './Modal'
import { RefMulti, RefSelect } from './RefSelect'
import { t } from '../i18n'

const WIDE_TYPES = new Set(['textarea', 'secretText', 'lines', 'tags', 'kv', 'refmulti', 'interface', 'bool'])

export function emptyValue(field) {
  if (field.type === 'bool') return false
  if (field.type === 'refmulti' || field.type === 'tags') return []
  if (field.type === 'kv') return {}
  return ''
}

function initialValues(fields, item, preset) {
  const values = {}
  for (const f of fields) {
    const source = item ? item[f.name] : preset[f.name] ?? f.default
    if (f.type === 'secret' || f.type === 'secretText') values[f.name] = '' // i segreti non tornano mai dall'API
    else if (f.type === 'lines') values[f.name] = (source || []).join('\n')
    else values[f.name] = source ?? emptyValue(f)
  }
  return values
}

export function isEmpty(value) {
  return value === '' || value === null || value === undefined
}

/** Valore del modulo -> valore da mandare all'API (undefined = non inviare) */
export function convert(field, value, isEdit) {
  switch (field.type) {
    case 'secret':
    case 'secretText':
      // In modifica un campo vuoto lascia il segreto salvato com'è
      return value ? value : isEdit ? undefined : null
    case 'lines':
      return String(value || '').split('\n').map((line) => line.trim()).filter(Boolean)
    case 'number':
    case 'ref':
    case 'interface':
      return isEmpty(value) ? null : Number(value)
    case 'refmulti':
      return (value || []).map(Number)
    case 'tags':
      return (value || []).map((v) => v.trim()).filter(Boolean)
    case 'bool':
      return Boolean(value)
    case 'kv':
      return value || {}
    default: {
      const text = String(value ?? '').trim()
      return text === '' ? null : text
    }
  }
}

export function FieldControl({ field, value, values, fields, onChange, disabled, editingId, item }) {
  const id = `field-${field.name}`
  switch (field.type) {
    case 'textarea':
      return <textarea id={id} className="input" rows={3} value={value} disabled={disabled} onChange={(e) => onChange(e.target.value)} />
    case 'lines':
      return (
        <textarea id={id} className="input mono" rows={4} value={value} placeholder={field.placeholder} disabled={disabled}
          onChange={(e) => onChange(e.target.value)} />
      )
    case 'tags':
      return (
        <ChipInput id={id} value={value} onChange={onChange} placeholder={field.placeholder} disabled={disabled}
          validate={field.validate} summary={field.summary} label={field.label} />
      )
    case 'secret':
      return (
        <input id={id} type="password" className="input" value={value} autoComplete="new-password" disabled={disabled}
          placeholder={field.savedHint?.(item) ?? field.placeholder} onChange={(e) => onChange(e.target.value)} />
      )
    case 'secretText': // segreto su più righe (chiave privata): come secret, ma in un'area di testo
      return (
        <textarea id={id} className="input mono" rows={4} value={value} autoComplete="off" spellCheck={false} disabled={disabled}
          placeholder={field.savedHint?.(item) ?? field.placeholder} onChange={(e) => onChange(e.target.value)} />
      )
    case 'number':
      return (
        <input id={id} type="number" className="input" value={value} placeholder={field.placeholder} disabled={disabled}
          onChange={(e) => onChange(e.target.value)} />
      )
    case 'select':
      return (
        <select id={id} className="input" value={value ?? ''} disabled={disabled} onChange={(e) => onChange(e.target.value)}>
          {!field.required && <option value="">{field.emptyLabel ?? '—'}</option>}
          {field.options.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
      )
    case 'ref': {
      const parentValue = field.dependsOn ? values[field.dependsOn] : null
      const waiting = field.dependsOn && isEmpty(parentValue)
      const params = field.dependsOn ? { [field.dependsOn]: parentValue, ...field.params } : field.params
      return (
        <RefSelect id={id} resource={field.ref} value={value} onChange={onChange} disabled={disabled} params={params}
          waitLabel={waiting ? field.waitLabel || t('Compila prima il campo collegato') : undefined}
          emptyLabel={field.required ? t('Scegli…') : field.emptyLabel ?? '—'} />
      )
    }
    case 'refmulti':
      return <RefMulti resource={field.ref} value={value} onChange={onChange} ordered={field.ordered} />
    case 'interface':
      return <InterfacePicker value={value || null} onChange={onChange} freeOnly={field.freeOnly} currentCableId={editingId} label={field.label} />
    case 'kv':
      return <KeyValueEditor value={value} onChange={onChange} />
    case 'color':
      return (
        <div className="color-field">
          <input type="color" value={value || '#888780'} onChange={(e) => onChange(e.target.value)} aria-label={`${field.label}: ${t('scegli')}`} disabled={disabled} />
          <input id={id} className="input mono" value={value} placeholder={t('#RRGGBB')} onChange={(e) => onChange(e.target.value)} disabled={disabled} />
        </div>
      )
    default:
      return (
        <input id={id} className="input" value={value} placeholder={field.placeholder} disabled={disabled}
          onChange={(e) => onChange(e.target.value)} />
      )
  }
}

/**
 * Casella sì/no. Con field.lockedBy = { url(values), reason(dati, values, item) } la casella si blocca
 * (spenta) quando reason restituisce un testo, che compare come spiegazione: es. un solo IP di management.
 */
function BoolField({ field, value, values, item, onChange }) {
  const url = field.lockedBy?.url(values) ?? null
  const { data } = useApi(url)
  const reason = url && data ? field.lockedBy.reason(data, values, item) : null
  return (
    <div className="field field--wide">
      <label className={`check${reason ? ' check--locked' : ''}`}>
        <input type="checkbox" checked={Boolean(value) && !reason} disabled={Boolean(reason)}
          onChange={(e) => onChange(e.target.checked)} />
        {field.label}
      </label>
      {reason ? <span className="hint">{reason}</span> : field.help && <span className="hint">{field.help}</span>}
    </div>
  )
}

/** Modulo di creazione/modifica generato dalla configurazione in resources.jsx */
export default function ResourceForm({ resourceKey, item = null, preset = {}, onClose, onSaved }) {
  const config = resources[resourceKey]
  const isEdit = Boolean(item)
  const [values, setValues] = useState(() => initialValues(config.fields, item, preset))
  const [error, setError] = useState(null)
  const [saving, setSaving] = useState(false)

  // Campi con fillFrom = { field, resource, key, hint }: li decide un altro campo (es. la posizione dal rack).
  // Quando quello ha un valore leggo l'elemento scelto e ne copio la chiave; finché la copia vale il campo è bloccato.
  const [filled, setFilled] = useState({})
  const fillers = config.fields.filter((f) => f.fillFrom)
  const fillKey = fillers.map((f) => `${f.name}=${values[f.fillFrom.field] ?? ''}`).join('&')
  useEffect(() => {
    let alive = true
    for (const f of fillers) {
      const source = values[f.fillFrom.field]
      if (isEmpty(source)) {
        setFilled((prev) => ({ ...prev, [f.name]: false }))
        continue
      }
      api.get(`/${resources[f.fillFrom.resource].path}/${source}`).then((obj) => {
        if (!alive) return
        const value = obj?.[f.fillFrom.key]
        setFilled((prev) => ({ ...prev, [f.name]: value != null }))
        if (value != null) setValues((prev) => ({ ...prev, [f.name]: value }))
      }).catch(() => {})
    }
    return () => {
      alive = false
    }
  }, [fillKey]) // eslint-disable-line react-hooks/exhaustive-deps

  const setValue = (name, value) =>
    setValues((prev) => {
      const next = { ...prev, [name]: value }
      // Se cambia la sede, svuoto posizione/rack che dipendevano da lei
      for (const f of config.fields) if (f.dependsOn === name && prev[name] !== value) next[f.name] = emptyValue(f)
      return next
    })

  const submit = async (e) => {
    e.preventDefault()
    e.stopPropagation() // un modulo aperto da un menu di un altro modulo: l'invio non deve arrivare a quello
    const payload = {}
    for (const f of config.fields) {
      if (isEdit && (f.createOnly || f.lockedFor?.(item))) continue
      const visible = !f.showIf || f.showIf(values, item)
      const missing = f.type === 'refmulti' || f.type === 'tags' ? !(values[f.name] || []).length : isEmpty(values[f.name])
      if (visible && (f.required || (f.requiredOnCreate && !isEdit)) && missing) {
        setError(t('Compila il campo "{field}".', { field: f.label }))
        return
      }
      const v = visible ? convert(f, values[f.name], isEdit) : f.hiddenValue
      if (v === undefined || (!isEdit && v === null)) continue
      payload[f.name] = v
    }
    setSaving(true)
    setError(null)
    try {
      const saved = isEdit
        ? await api.patch(`/${config.path}/${item.id}`, payload)
        : await api.post(`/${config.path}`, payload)
      invalidate()
      onSaved?.(saved)
    } catch (err) {
      setError(err.message)
      setSaving(false)
    }
  }

  return (
    <Modal title={isEdit ? config.editLabel : config.newLabel} onClose={onClose} wide={config.fields.length > 6}>
      <form className="form" onSubmit={submit} noValidate>
        <div className="form__grid">
          {config.fields.map((f) => {
            if (f.showIf && !f.showIf(values, item)) return null
            // lockedFor(item): motivo per cui quel campo di quell'elemento non si cambia (non si invia)
            const lockReason = isEdit ? f.lockedFor?.(item) : null
            const locked = (isEdit && f.createOnly) || Boolean(lockReason)
            const disabled = locked || Boolean(filled[f.name])
            const wide = WIDE_TYPES.has(f.type)
            if (f.type === 'bool') {
              return <BoolField key={f.name} field={f} value={values[f.name]} values={values} item={item} onChange={(v) => setValue(f.name, v)} />
            }
            const labelIsElement = !['interface', 'refmulti', 'kv'].includes(f.type)
            const Label = labelIsElement ? 'label' : 'span'
            return (
              <div key={f.name} className={`field${wide ? ' field--wide' : ''}`}>
                <Label className="field__label" {...(labelIsElement ? { htmlFor: `field-${f.name}` } : {})}>
                  {f.label}
                  {(f.required || (f.requiredOnCreate && !isEdit)) && <span className="field__req" aria-hidden="true"> *</span>}
                </Label>
                <FieldControl field={f} value={values[f.name]} values={values} fields={config.fields}
                  onChange={(v) => setValue(f.name, v)} disabled={disabled} editingId={item?.id} item={item} />
                {locked && <span className="hint">{lockReason || t('Non modificabile dopo la creazione.')}</span>}
                {!locked && filled[f.name] && <span className="hint">{f.fillFrom.hint}</span>}
                {!disabled && f.help && <span className="hint">{f.help}</span>}
              </div>
            )
          })}
        </div>
        {error && (
          <p className="form__error" role="alert">
            {error}
          </p>
        )}
        <div className="modal__footer">
          <button type="button" className="btn btn--ghost" onClick={onClose}>
            {t('Annulla')}
          </button>
          <button type="submit" className="btn btn--primary" disabled={saving}>
            {saving ? t('Salvataggio…') : isEdit ? t('Salva modifiche') : t('Crea')}
          </button>
        </div>
      </form>
    </Modal>
  )
}
