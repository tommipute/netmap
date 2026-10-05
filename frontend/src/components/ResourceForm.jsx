import { useState } from 'react'
import { api } from '../api'
import { invalidate } from '../hooks'
import { resources } from '../resources'
import InterfacePicker from './InterfacePicker'
import KeyValueEditor from './KeyValueEditor'
import Modal from './Modal'
import { RefMulti, RefSelect } from './RefSelect'

const WIDE_TYPES = new Set(['textarea', 'kv', 'refmulti', 'interface', 'bool'])

function emptyValue(field) {
  if (field.type === 'bool') return false
  if (field.type === 'refmulti') return []
  if (field.type === 'kv') return {}
  return ''
}

function initialValues(fields, item, preset) {
  const values = {}
  for (const f of fields) {
    const source = item ? item[f.name] : preset[f.name] ?? f.default
    values[f.name] = source ?? emptyValue(f)
  }
  return values
}

function isEmpty(value) {
  return value === '' || value === null || value === undefined
}

/** Valore del modulo -> valore da mandare all'API */
function convert(field, value) {
  switch (field.type) {
    case 'number':
    case 'ref':
    case 'interface':
      return isEmpty(value) ? null : Number(value)
    case 'refmulti':
      return (value || []).map(Number)
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

function FieldControl({ field, value, values, fields, onChange, disabled, editingId }) {
  const id = `field-${field.name}`
  switch (field.type) {
    case 'textarea':
      return <textarea id={id} className="input" rows={3} value={value} disabled={disabled} onChange={(e) => onChange(e.target.value)} />
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
          waitLabel={waiting ? field.waitLabel || 'Compila prima il campo collegato' : undefined}
          emptyLabel={field.required ? 'Scegli…' : field.emptyLabel ?? '—'} />
      )
    }
    case 'refmulti':
      return <RefMulti resource={field.ref} value={value} onChange={onChange} />
    case 'interface':
      return <InterfacePicker value={value || null} onChange={onChange} freeOnly={field.freeOnly} currentCableId={editingId} label={field.label} />
    case 'kv':
      return <KeyValueEditor value={value} onChange={onChange} />
    case 'color':
      return (
        <div className="color-field">
          <input type="color" value={value || '#888780'} onChange={(e) => onChange(e.target.value)} aria-label={`${field.label}: scegli`} disabled={disabled} />
          <input id={id} className="input mono" value={value} placeholder="#RRGGBB" onChange={(e) => onChange(e.target.value)} disabled={disabled} />
        </div>
      )
    default:
      return (
        <input id={id} className="input" value={value} placeholder={field.placeholder} disabled={disabled}
          onChange={(e) => onChange(e.target.value)} />
      )
  }
}

/** Modulo di creazione/modifica generato dalla configurazione in resources.jsx */
export default function ResourceForm({ resourceKey, item = null, preset = {}, onClose, onSaved }) {
  const config = resources[resourceKey]
  const isEdit = Boolean(item)
  const [values, setValues] = useState(() => initialValues(config.fields, item, preset))
  const [error, setError] = useState(null)
  const [saving, setSaving] = useState(false)

  const setValue = (name, value) =>
    setValues((prev) => {
      const next = { ...prev, [name]: value }
      // Se cambia la sede, svuoto posizione/rack che dipendevano da lei
      for (const f of config.fields) if (f.dependsOn === name && prev[name] !== value) next[f.name] = emptyValue(f)
      return next
    })

  const submit = async (e) => {
    e.preventDefault()
    const payload = {}
    for (const f of config.fields) {
      if (isEdit && f.createOnly) continue
      const visible = !f.showIf || f.showIf(values)
      if (visible && f.required && isEmpty(values[f.name])) {
        setError(`Compila il campo "${f.label}".`)
        return
      }
      const v = visible ? convert(f, values[f.name]) : f.hiddenValue
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
            if (f.showIf && !f.showIf(values)) return null
            const disabled = isEdit && f.createOnly
            const wide = WIDE_TYPES.has(f.type)
            if (f.type === 'bool') {
              return (
                <div key={f.name} className="field field--wide">
                  <label className="check">
                    <input type="checkbox" checked={Boolean(values[f.name])} onChange={(e) => setValue(f.name, e.target.checked)} />
                    {f.label}
                  </label>
                  {f.help && <span className="hint">{f.help}</span>}
                </div>
              )
            }
            const labelIsElement = !['interface', 'refmulti', 'kv'].includes(f.type)
            const Label = labelIsElement ? 'label' : 'span'
            return (
              <div key={f.name} className={`field${wide ? ' field--wide' : ''}`}>
                <Label className="field__label" {...(labelIsElement ? { htmlFor: `field-${f.name}` } : {})}>
                  {f.label}
                  {f.required && <span className="field__req" aria-hidden="true"> *</span>}
                </Label>
                <FieldControl field={f} value={values[f.name]} values={values} fields={config.fields}
                  onChange={(v) => setValue(f.name, v)} disabled={disabled} editingId={item?.id} />
                {disabled && <span className="hint">Non modificabile dopo la creazione.</span>}
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
            Annulla
          </button>
          <button type="submit" className="btn btn--primary" disabled={saving}>
            {saving ? 'Salvataggio…' : isEdit ? 'Salva modifiche' : 'Crea'}
          </button>
        </div>
      </form>
    </Modal>
  )
}
