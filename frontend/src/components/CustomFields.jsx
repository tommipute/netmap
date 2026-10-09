import { useOptions } from '../hooks'
import { LOCALE, t } from '../i18n'
import KeyValueEditor from './KeyValueEditor'
import { resources } from '../resources'

// Campi personalizzati definiti dall'amministratore (Amministrazione → Campi personalizzati): i valori stanno in
// custom_fields di ogni oggetto; le chiavi senza definizione (es. arrivate da un import) restano campi liberi.

export const CUSTOM_FIELD_TYPES = [
  { value: 'text', label: t('Testo') },
  { value: 'longtext', label: t('Testo lungo') },
  { value: 'number', label: t('Numero') },
  { value: 'bool', label: t('Sì / no') },
  { value: 'date', label: t('Data') },
  { value: 'select', label: t('Scelta da un elenco') },
  { value: 'url', label: t('Link') },
]

/** Definizioni che valgono per un tipo di oggetto (il percorso dell'API: devices, sites…), in ordine. */
export function useCustomFields(objectType) {
  return useOptions(objectType ? 'custom-fields' : null).filter((d) => (d.object_types || []).includes(objectType))
}

const isEmpty = (value) => value === null || value === undefined || value === ''

/** Valore leggibile (tabelle e schede). */
export function CustomValue({ definition, value }) {
  if (isEmpty(value)) return <span className="muted">—</span>
  switch (definition?.type) {
    case 'bool':
      return value === true || value === 'true' ? t('Sì') : t('No')
    case 'number':
      return typeof value === 'number' ? value.toLocaleString(LOCALE) : String(value)
    case 'date': {
      const day = new Date(`${value}T00:00:00`)
      return Number.isNaN(day.getTime()) ? String(value) : day.toLocaleDateString(LOCALE)
    }
    case 'url':
      return (
        <a href={String(value)} target="_blank" rel="noreferrer noopener" onClick={(e) => e.stopPropagation()}>
          {String(value).replace(/^https?:\/\//, '')}
        </a>
      )
    default:
      return String(value)
  }
}

/** Colonne delle tabelle per i campi definiti: si filtrano e ordinano come cf_<nome>. */
export function customColumns(definitions) {
  return definitions.map((d) => {
    const filter =
      d.type === 'select' ? { kind: 'options', options: d.choices.map((c) => ({ value: c, label: c })) }
        : d.type === 'bool' ? { kind: 'options', options: [{ value: 'true', label: t('Sì') }, { value: 'false', label: t('No') }] }
          : { kind: 'text' }
    return {
      name: `cf_${d.name}`,
      label: d.label,
      render: (o) => <CustomValue definition={d} value={o.custom_fields?.[d.name]} />,
      filter,
      sortField: d.type === 'longtext' ? null : `cf_${d.name}`,
    }
  })
}

function CustomControl({ definition, value, onChange }) {
  const id = `cf-${definition.name}`
  const common = { id, className: 'input', value: value ?? '', onChange: (e) => onChange(e.target.value) }
  switch (definition.type) {
    case 'longtext':
      return <textarea rows={3} {...common} />
    case 'number':
      return <input type="number" step="any" {...common} />
    case 'date':
      return <input type="date" {...common} />
    case 'url':
      return <input type="url" placeholder="https://…" {...common} />
    case 'bool':
      return (
        <select {...common} value={value === true || value === 'true' ? 'true' : value === false || value === 'false' ? 'false' : ''}
          onChange={(e) => onChange(e.target.value === '' ? '' : e.target.value === 'true')}>
          <option value="">—</option>
          <option value="true">{t('Sì')}</option>
          <option value="false">{t('No')}</option>
        </select>
      )
    case 'select':
      return (
        <select {...common}>
          <option value="">—</option>
          {definition.choices.map((c) => <option key={c} value={c}>{c}</option>)}
        </select>
      )
    default:
      return <input {...common} />
  }
}

/** Campo "custom_fields" dei moduli: un controllo per campo definito, sotto i campi liberi. */
export function CustomFieldsEditor({ value, onChange, resourceKey }) {
  const definitions = useCustomFields(resourceKey)
  const values = value || {}
  const defined = new Set(definitions.map((d) => d.name))
  const free = Object.fromEntries(Object.entries(values).filter(([k]) => !defined.has(k)))
  const setDefined = (name, v) => onChange({ ...values, [name]: v })
  // I campi liberi cambiano tutti insieme: tengo i definiti e sostituisco il resto
  const setFree = (next) => onChange({ ...Object.fromEntries(Object.entries(values).filter(([k]) => defined.has(k))), ...next })
  return (
    <div className="custom-fields">
      {definitions.length > 0 && (
        <div className="custom-fields__grid">
          {definitions.map((d) => (
            <div key={d.name} className={`field${d.type === 'longtext' ? ' field--wide' : ''}`}>
              <label className="field__label" htmlFor={`cf-${d.name}`}>
                {d.label}
                {d.required && <span className="field__req" aria-hidden="true"> *</span>}
              </label>
              <CustomControl definition={d} value={values[d.name]} onChange={(v) => setDefined(d.name, v)} />
              {d.description && <span className="hint">{d.description}</span>}
            </div>
          ))}
        </div>
      )}
      <div className="custom-fields__free">
        {definitions.length > 0 && <span className="hint">{t('Altri campi, liberi (nome e valore):')}</span>}
        <KeyValueEditor value={free} onChange={setFree} />
      </div>
    </div>
  )
}

// Oggetti che possono avere campi personalizzati (come OBJECT_TYPES del backend), nell'ordine del menu
export const CUSTOM_FIELD_OBJECTS = ['devices', 'interfaces', 'cables', 'sites', 'locations', 'racks', 'device-types',
  'prefixes', 'ip-addresses', 'vlans', 'vrfs']

/** Scelta degli oggetti a cui si applica un campo: pastiglie da accendere. */
export function ObjectTypesPicker({ value, onChange }) {
  const selected = value || []
  const toggle = (key) => onChange(selected.includes(key) ? selected.filter((v) => v !== key) : [...selected, key])
  return (
    <div className="chips" role="group">
      {CUSTOM_FIELD_OBJECTS.map((key) => {
        const on = selected.includes(key)
        return (
          <button type="button" key={key} className={`chip${on ? ' chip--on' : ''}`} aria-pressed={on} onClick={() => toggle(key)}>
            {resources[key].title}
          </button>
        )
      })}
    </div>
  )
}
