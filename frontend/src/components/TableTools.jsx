import { useEffect, useMemo, useRef, useState } from 'react'
import { useOptions } from '../hooks'
import { resources } from '../resources'
import { IconButton } from './Icon'
import { t } from '../i18n'

/*
 * Strumenti delle tabelle degli elenchi (ResourcePage):
 * - colonne da mostrare/nascondere e riordinare, salvate nel browser per ogni elenco (useTableColumns, ColumnsMenu)
 * - riga di filtri sotto le intestazioni (filterSpec, ColumnFilter, filterParams) -> parametri <campo>__contains,
 *   <campo>__eq, <campo>__isnull dell'API
 * - ordinamento cliccando l'intestazione (sortFieldOf) -> parametro sort
 * Nelle colonne di resources.jsx: hidden (nascosta finché non la si sceglie), filter (false o
 * { kind: 'text' | 'options' | 'ref', field, options, ref, emptyLabel }), sortField (campo per l'ordinamento).
 */

const EMPTY = '__empty__' // valore dei menu dei filtri per "campo vuoto"
const BOOL_OPTIONS = [{ value: 'true', label: t('Sì') }, { value: 'false', label: t('No') }]

const storageKey = (resourceKey) => `netmap.table.${resourceKey}`

function readSaved(resourceKey) {
  try {
    const saved = JSON.parse(localStorage.getItem(storageKey(resourceKey)) || 'null')
    return Array.isArray(saved) ? saved : null
  } catch {
    return null
  }
}

/** Colonne nell'ordine scelto, con visible; quelle nuove (non ancora salvate) in fondo, visibili se non hidden. */
export function useTableColumns(resourceKey, columns) {
  const [saved, setSaved] = useState(() => readSaved(resourceKey))
  const layout = useMemo(() => {
    const byName = new Map(columns.map((c) => [c.name, c]))
    const known = (saved || []).filter((s) => byName.has(s.name))
    const missing = columns.filter((c) => !known.some((s) => s.name === c.name)).map((c) => ({ name: c.name, visible: !c.hidden }))
    return [...known, ...missing].map((s) => ({ column: byName.get(s.name), visible: s.visible }))
  }, [columns, saved])

  const save = (next) => {
    let plain = next ? next.map((l) => ({ name: l.column.name, visible: l.visible })) : null
    // Tornata uguale alla predefinita (stesso ordine, stesse colonne visibili): non è più una scelta da ricordare
    const defaults = columns.map((c) => ({ name: c.name, visible: !c.hidden }))
    if (plain && JSON.stringify(plain) === JSON.stringify(defaults)) plain = null
    setSaved(plain)
    try {
      if (plain) localStorage.setItem(storageKey(resourceKey), JSON.stringify(plain))
      else localStorage.removeItem(storageKey(resourceKey))
    } catch {
      // senza storage la scelta vale solo per questa pagina
    }
  }
  // Anche una scelta salvata prima di questa regola, se coincide con la predefinita, non accende il pulsante
  const plain = JSON.stringify(layout.map((l) => ({ name: l.column.name, visible: l.visible })))
  const customized = Boolean(saved) && plain !== JSON.stringify(columns.map((c) => ({ name: c.name, visible: !c.hidden })))
  return { layout, visible: layout.filter((l) => l.visible).map((l) => l.column), save, customized }
}

/** Menu "Colonne": spunta per mostrarle, frecce per spostarle, ripristino delle predefinite. */
export function ColumnsMenu({ layout, save, customized }) {
  const [open, setOpen] = useState(false)
  const boxRef = useRef(null)
  useEffect(() => {
    if (!open) return undefined
    const close = (e) => !boxRef.current?.contains(e.target) && setOpen(false)
    const esc = (e) => e.key === 'Escape' && setOpen(false)
    document.addEventListener('mousedown', close)
    document.addEventListener('keydown', esc)
    return () => {
      document.removeEventListener('mousedown', close)
      document.removeEventListener('keydown', esc)
    }
  }, [open])

  const move = (index, delta) => {
    const next = [...layout]
    const [item] = next.splice(index, 1)
    next.splice(index + delta, 0, item)
    save(next)
  }
  const toggle = (index, visible) => {
    if (!visible && layout.filter((l) => l.visible).length === 1) return // almeno una colonna
    save(layout.map((l, i) => (i === index ? { ...l, visible } : l)))
  }

  return (
    <div className="columns-menu" ref={boxRef}>
      <IconButton icon="columns" label={t('Colonne della tabella')} className={customized ? 'is-on' : ''}
        aria-expanded={open} onClick={() => setOpen((v) => !v)} />
      {open && (
        <div className="columns-menu__panel" role="dialog" aria-label={t('Colonne della tabella')}>
          <p className="columns-menu__title">{t('Colonne')}</p>
          <ul>
            {layout.map((l, i) => (
              <li key={l.column.name}>
                <label className="check">
                  <input type="checkbox" checked={l.visible} onChange={(e) => toggle(i, e.target.checked)} />
                  {l.column.label}
                </label>
                <IconButton icon="up" label={t('Sposta {name} prima', { name: l.column.label })} small className="btn--ghost" disabled={i === 0} onClick={() => move(i, -1)} />
                <IconButton icon="down" label={t('Sposta {name} dopo', { name: l.column.label })} small className="btn--ghost" disabled={i === layout.length - 1} onClick={() => move(i, 1)} />
              </li>
            ))}
          </ul>
          {customized && (
            <div className="columns-menu__footer">
              <IconButton icon="refresh" label={t('Torna alle colonne predefinite')} small className="btn--ghost" onClick={() => save(null)} />
            </div>
          )}
        </div>
      )}
    </div>
  )
}

/** Che filtro ha una colonna (null = nessuno). Le colonne con render lo dichiarano, le altre lo ricavano dal tipo. */
export function filterSpec(column) {
  if (column.filter === false) return null
  if (column.filter) return { field: column.name, ...column.filter }
  if (column.render) return null
  switch (column.type) {
    case 'ref':
      return { kind: 'ref', field: column.name, ref: column.ref }
    case 'badge':
    case 'select':
      return { kind: 'options', field: column.name, options: column.options }
    case 'bool':
      return { kind: 'options', field: column.name, options: BOOL_OPTIONS }
    case 'color':
      return null
    default:
      return { kind: 'text', field: column.name }
  }
}

/** Campo per l'ordinamento cliccando l'intestazione (null = non ordinabile). */
export function sortFieldOf(column) {
  if (column.sortField !== undefined) return column.sortField
  if (column.render || column.type === 'ref' || column.type === 'color') return null
  return column.name
}

/** Parametri dell'API per i filtri compilati: { nome_colonna: valore } -> { campo__op: valore }. */
export function filterParams(columns, values) {
  const out = {}
  for (const column of columns) {
    const spec = filterSpec(column)
    const value = values[column.name]
    if (!spec || value === undefined || value === '') continue
    if (spec.kind === 'text') out[`${spec.field}__contains`] = value
    else if (value === EMPTY) out[`${spec.field}__isnull`] = 'true'
    else out[`${spec.field}__eq`] = value
  }
  return out
}

function RefFilter({ spec, value, onChange, label }) {
  const config = resources[spec.ref]
  const items = useOptions(config.path)
  return (
    <select className="input input--sm" value={value ?? ''} onChange={(e) => onChange(e.target.value)} aria-label={t('Filtro: {name}', { name: label })}>
      <option value="">{t('Tutti')}</option>
      <option value={EMPTY}>{t('(vuoto)')}</option>
      {items.map((o) => <option key={o.id} value={o.id}>{config.label(o)}</option>)}
    </select>
  )
}

/** Il controllo nella riga dei filtri, sotto l'intestazione della colonna. */
export function ColumnFilter({ column, value, onChange }) {
  const spec = filterSpec(column)
  if (!spec) return null
  if (spec.kind === 'text') {
    return (
      <input type="search" className="input input--sm" value={value ?? ''} placeholder={t('contiene…')}
        aria-label={t('Filtro: {name}', { name: column.label })} onChange={(e) => onChange(e.target.value)} />
    )
  }
  if (spec.kind === 'ref') return <RefFilter spec={spec} value={value} onChange={onChange} label={column.label} />
  return (
    <select className="input input--sm" value={value ?? ''} onChange={(e) => onChange(e.target.value)} aria-label={t('Filtro: {name}', { name: column.label })}>
      <option value="">{t('Tutti')}</option>
      {spec.empty !== false && <option value={EMPTY}>{spec.emptyLabel || t('(vuoto)')}</option>}
      {spec.options.map((o) => <option key={String(o.value)} value={o.value}>{o.label}</option>)}
    </select>
  )
}
