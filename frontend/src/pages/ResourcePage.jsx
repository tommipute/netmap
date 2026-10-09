import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { api, qs } from '../api'
import { useAuth } from '../auth'
import { Badge, ErrorBox, Loading, Mono } from '../components/Bits'
import BulkEditDialog from '../components/BulkEditDialog'
import { customColumns, useCustomFields } from '../components/CustomFields'
import DeleteDialog from '../components/DeleteDialog'
import DeviceImportDialog from '../components/DeviceImportDialog'
import { IconButton } from '../components/Icon'
import RefLabel from '../components/RefLabel'
import { RefSelect } from '../components/RefSelect'
import ResourceForm from '../components/ResourceForm'
import { ColumnFilter, ColumnsMenu, filterParams, filterSpec, sortFieldOf, useTableColumns } from '../components/TableTools'
import { invalidate, useApi, useDebounced } from '../hooks'
import { labelOf } from '../options'
import { resources } from '../resources'
import { t, tn } from '../i18n'

const LIMIT = 50

// view.tree: elenco nell'ordine predefinito (es. posizioni ad albero), non ordinato per una colonna
function Cell({ column, row, view }) {
  if (column.render) return column.render(row, view)
  const value = row[column.name]
  switch (column.type) {
    case 'ref':
      return <RefLabel resource={column.ref} id={value} empty={column.empty} />
    case 'badge':
      return <Badge value={value} options={column.options} />
    case 'select':
      return value ? labelOf(column.options, value) : <span className="muted">—</span>
    case 'mono':
      return <Mono>{value}</Mono>
    case 'bool':
      return value ? t('Sì') : t('No')
    case 'color':
      return <span className="swatch" style={{ background: value }} title={value} />
    default:
      return value ?? <span className="muted">—</span>
  }
}

function Filter({ filter, value, onChange }) {
  if (filter.ref) {
    return (
      <RefSelect resource={filter.ref} value={value} onChange={onChange} emptyLabel={t('{name}: tutti', { name: filter.label })} ariaLabel={filter.label} />
    )
  }
  return (
    <select className="input" value={value} onChange={(e) => onChange(e.target.value)} aria-label={filter.label}>
      <option value="">{t('{name}: tutti', { name: filter.label })}</option>
      {filter.options.map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </select>
  )
}

export default function ResourcePage({ resourceKey }) {
  const config = resources[resourceKey]
  const navigate = useNavigate()
  const { canEdit } = useAuth()
  const [params, setParams] = useSearchParams()
  const [search, setSearch] = useState('')
  // Filtri della barra: stanno nell'indirizzo (es. /devices?reachable=false), così un link verso la stessa pagina
  // con altri filtri (i pallini dello stato live in alto) aggiorna l'elenco, e funzionano Indietro e i link condivisi
  const filtersKey = (config.filters || []).map((f) => `${f.name}=${params.get(f.name) ?? ''}`).join('&')
  const filters = useMemo(
    () => Object.fromEntries((config.filters || []).filter((f) => params.get(f.name)).map((f) => [f.name, params.get(f.name)])),
    [filtersKey], // eslint-disable-line react-hooks/exhaustive-deps
  )
  const setFilter = (name, value) =>
    setParams((prev) => {
      const next = new URLSearchParams(prev)
      if (value === '' || value === null || value === undefined) next.delete(name)
      else next.set(name, String(value))
      return next
    }, { replace: true })
  const [offset, setOffset] = useState(0)
  useEffect(() => setOffset(0), [filtersKey])
  const [editing, setEditing] = useState(null) // null | 'new' | elemento
  const [importing, setImporting] = useState(false)
  const [selected, setSelected] = useState(() => new Map()) // id -> elemento, solo nella pagina visibile
  const [bulkEditing, setBulkEditing] = useState(false)
  const [deleting, setDeleting] = useState(null) // elementi da eliminare con le opzioni della risorsa
  const [bulkBusy, setBulkBusy] = useState(null) // "Elimino 3 di 10…"
  const [bulkResult, setBulkResult] = useState(null) // { done, failed: [{ label, error }], verb }
  const q = useDebounced(search)
  // Tabella: colonne scelte (salvate nel browser), filtri sotto le intestazioni, ordinamento
  // In fondo una colonna per ogni campo personalizzato definito per questi oggetti
  const definitions = useCustomFields(config.fields.some((f) => f.name === 'custom_fields') ? config.path : null)
  const definitionsKey = JSON.stringify(definitions)
  const allColumns = useMemo(() => [...config.columns, ...customColumns(definitions)], [config.columns, definitionsKey]) // eslint-disable-line react-hooks/exhaustive-deps
  const { layout, visible: columns, save: saveColumns, customized } = useTableColumns(resourceKey, allColumns)
  const [showColumnFilters, setShowColumnFilters] = useState(false)
  const [columnFilters, setColumnFilters] = useState({})
  const [sort, setSort] = useState(null) // "campo" o "-campo"
  // Ritardo di battitura su una stringa (un oggetto nuovo a ogni render farebbe ripartire il timer all'infinito)
  const columnQueryKey = useDebounced(JSON.stringify(filterParams(columns, columnFilters)))
  const columnQuery = useMemo(() => JSON.parse(columnQueryKey), [columnQueryKey])

  const { data, error, loading, reload } = useApi(
    `/${config.path}${qs({ limit: LIMIT, offset, q, ...filters, ...columnQuery, sort })}`,
  )
  const filtered = Boolean(q) || Object.values(filters).some((v) => v !== '' && v !== undefined) || columnQueryKey !== '{}'

  const setColumnFilter = (name, value) => {
    setColumnFilters((prev) => ({ ...prev, [name]: value }))
    setOffset(0)
  }
  const toggleColumnFilters = () => {
    if (showColumnFilters) setColumnFilters({}) // spenti: niente filtri nascosti che restano attivi
    setShowColumnFilters((v) => !v)
    setOffset(0)
  }
  const sortBy = (field) => {
    setSort((current) => (current === field ? `-${field}` : current === `-${field}` ? null : field))
    setOffset(0)
  }

  const open = (item) => (config.detail ? navigate(config.detail(item)) : setEditing(item))

  // Cambiando pagina, ricerca o filtri la selezione riparte da zero
  useEffect(() => setSelected(new Map()), [q, filters, offset, columnQueryKey, sort])
  const items = data?.items || []
  const view = { tree: !sort }
  const allSelected = items.length > 0 && items.every((item) => selected.has(item.id))
  const toggleItem = (item, on) =>
    setSelected((prev) => {
      const next = new Map(prev)
      if (on) next.set(item.id, item)
      else next.delete(item.id)
      return next
    })
  const toggleAll = (on) => setSelected(on ? new Map(items.map((item) => [item.id, item])) : new Map())

  const bulkDone = (result) => {
    setBulkEditing(false)
    setBulkBusy(null)
    setBulkResult(result)
    setSelected(new Map())
    reload()
  }

  const removeSelected = async () => {
    const chosen = [...selected.values()]
    if (config.deleteOptions) {
      setDeleting(chosen)
      return
    }
    if (!window.confirm(tn(chosen.length, 'Eliminare 1 elemento? Non si può annullare.', 'Eliminare {n} elementi? Non si può annullare.'))) return
    const failed = []
    for (let i = 0; i < chosen.length; i++) {
      setBulkBusy(t('Elimino {i} di {n}…', { i: i + 1, n: chosen.length }))
      try {
        await api.del(`/${config.path}/${chosen[i].id}`)
      } catch (err) {
        failed.push({ label: config.label(chosen[i]), error: err.message })
      }
    }
    invalidate()
    bulkDone({ done: chosen.length - failed.length, failed, verb: 'eliminati' })
  }

  const handleExport = async (format = 'csv') => {
    try {
      const url = `/api/devices/export${qs({ format, q, ...filters, ...columnQuery })}`
      const res = await fetch(url)
      if (!res.ok) throw new Error(t("Errore durante l'esportazione dei device"))
      const blob = await res.blob()
      const a = document.createElement('a')
      a.href = URL.createObjectURL(blob)
      a.download = format === 'json' ? 'devices_export.json' : 'devices_export.csv'
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(a.href)
    } catch (err) {
      window.alert(err.message)
    }
  }

  const remove = async (item) => {
    if (config.deleteOptions) {
      setDeleting([item])
      return
    }
    if (!window.confirm(t('Eliminare "{name}"?', { name: config.label(item) }))) return
    try {
      await api.del(`/${config.path}/${item.id}`)
      invalidate()
      reload()
    } catch (err) {
      window.alert(err.message)
    }
  }

  const saved = (item) => {
    const wasNew = editing === 'new'
    setEditing(null)
    reload()
    if (wasNew && config.detail) navigate(config.detail(item))
  }

  return (
    <div className="page">
      <header className="page-head">
        <div>
          <h1>{config.title}</h1>
          {config.intro && <p className="page-intro">{config.intro}</p>}
        </div>
        <div className="page-head__actions">
          {resourceKey === 'devices' && (
            <>
              <IconButton icon="download" label={t('Esporta in CSV (si apre con Excel), con i filtri attivi')} onClick={() => handleExport('csv')}>
                <span className="btn__tag">{t('CSV')}</span>
              </IconButton>
              <IconButton icon="download" label={t('Esporta in JSON, con i filtri attivi')} onClick={() => handleExport('json')}>
                <span className="btn__tag">{t('JSON')}</span>
              </IconButton>
              {canEdit && <IconButton icon="upload" label={t('Importa device da un file CSV')} onClick={() => setImporting(true)} />}
            </>
          )}
          {canEdit && (
            <IconButton icon="plus" label={config.newLabel} className="btn--primary" onClick={() => setEditing('new')} />
          )}
        </div>
      </header>

      <div className="toolbar">
        <input
          type="search"
          className="input toolbar__search"
          placeholder={t('Cerca')}
          value={search}
          aria-label={t('Cerca in {name}', { name: config.title })}
          onChange={(e) => {
            setSearch(e.target.value)
            setOffset(0)
          }}
        />
        {(config.filters || []).map((f) => (
          <Filter
            key={f.name}
            filter={f}
            value={filters[f.name] ?? ''}
            onChange={(v) => setFilter(f.name, v)}
          />
        ))}
        <ColumnsMenu layout={layout} save={saveColumns} customized={customized} />
        {columns.some((c) => filterSpec(c)) && (
          <IconButton icon="filter" label={showColumnFilters ? t('Togli i filtri sulle colonne') : t('Filtri sulle colonne')}
            className={showColumnFilters ? 'is-on' : ''} aria-pressed={showColumnFilters} onClick={toggleColumnFilters} />
        )}
        {/* Con una selezione, al posto del conteggio compaiono le azioni: la tabella non si sposta */}
        {canEdit && selected.size > 0 ? (
          <div className="toolbar__count bulk-actions" role="region" aria-label={t('Elementi selezionati')}>
            <strong>{tn(selected.size, '1 selezionato', '{n} selezionati')}</strong>
            {bulkBusy ? (
              <span className="muted">{bulkBusy}</span>
            ) : (
              <>
                {config.bulkFields && (
                  <IconButton icon="edit" label={t('Modifica i selezionati')} small onClick={() => setBulkEditing(true)} />
                )}
                <IconButton icon="trash" label={t('Elimina i selezionati')} small danger onClick={removeSelected} />
                <IconButton icon="close" label={t('Togli la selezione')} small className="btn--ghost" onClick={() => toggleAll(false)} />
              </>
            )}
          </div>
        ) : (
          data && <span className="toolbar__count">{tn(data.total, '1 elemento', '{n} elementi')}</span>
        )}
      </div>

      {bulkResult && (
        <div className={`notice${bulkResult.failed.length ? ' notice--warn' : ''}`} role="status">
          {bulkResult.verb === 'eliminati' ? tn(bulkResult.done, '1 elemento eliminato.', '{n} elementi eliminati.') : tn(bulkResult.done, '1 elemento modificato.', '{n} elementi modificati.')}
          {bulkResult.failed.length > 0 && (
            <>
              {' '}Non riusciti:
              <ul>
                {bulkResult.failed.map((f) => <li key={f.label}>{f.label}: {f.error}</li>)}
              </ul>
            </>
          )}
          <IconButton icon="close" label={t('Chiudi il messaggio')} small className="btn--ghost notice__close" onClick={() => setBulkResult(null)} />
        </div>
      )}

      <ErrorBox error={error} />
      {!data && loading && <Loading />}

      {data && data.items.length === 0 && !showColumnFilters && (
        <div className="empty">
          {filtered ? (
            <p>{t('Nessun risultato con questi filtri.')}</p>
          ) : (
            <>
              <p>{t("Non c'è ancora niente qui.")}</p>
              {canEdit && (
                <IconButton icon="plus" label={config.newLabel} className="btn--primary" onClick={() => setEditing('new')} />
              )}
            </>
          )}
        </div>
      )}

      {data && (data.items.length > 0 || showColumnFilters) && (
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                {canEdit && (
                  <th className="table__select">
                    <input type="checkbox" checked={allSelected} aria-label={t('Seleziona tutti quelli della pagina')}
                      onChange={(e) => toggleAll(e.target.checked)} />
                  </th>
                )}
                {columns.map((c) => {
                  const field = sortFieldOf(c)
                  if (!field) return <th key={c.name}>{c.label}</th>
                  const state = sort === field ? 'ascending' : sort === `-${field}` ? 'descending' : 'none'
                  return (
                    <th key={c.name} aria-sort={state}>
                      <button type="button" className="th-sort" onClick={() => sortBy(field)}
                        title={state === 'ascending' ? t('Ordina al contrario') : state === 'descending' ? t("Togli l'ordinamento") : t('Ordina per {name}', { name: c.label })}>
                        {c.label}
                        <span className="th-sort__arrow" aria-hidden="true">{state === 'ascending' ? '▲' : state === 'descending' ? '▼' : ''}</span>
                      </button>
                    </th>
                  )
                })}
                <th className="table__actions">
                  <span className="sr-only">{t('Azioni')}</span>
                </th>
              </tr>
              {showColumnFilters && (
                <tr className="table__filters">
                  {canEdit && <th className="table__select" />}
                  {columns.map((c) => (
                    <th key={c.name}>
                      <ColumnFilter column={c} value={columnFilters[c.name]} onChange={(v) => setColumnFilter(c.name, v)} />
                    </th>
                  ))}
                  <th className="table__actions">
                    {columnQueryKey !== '{}' && (
                      <IconButton icon="close" label={t('Svuota i filtri sulle colonne')} small className="btn--ghost" onClick={() => setColumnFilters({})} />
                    )}
                  </th>
                </tr>
              )}
            </thead>
            <tbody>
              {data.items.map((item) => (
                <tr
                  key={item.id}
                  className={`table__row--link${selected.has(item.id) ? ' is-selected' : ''}`}
                  tabIndex={0}
                  onClick={() => (config.detail || canEdit) && open(item)}
                  onKeyDown={(e) => e.key === 'Enter' && e.target === e.currentTarget && (config.detail || canEdit) && open(item)}
                >
                  {canEdit && (
                    <td className="table__select" onClick={(e) => e.stopPropagation()}>
                      <input type="checkbox" checked={selected.has(item.id)} aria-label={`Seleziona ${item.name || item.id}`}
                        onChange={(e) => toggleItem(item, e.target.checked)} />
                    </td>
                  )}
                  {columns.map((c) => (
                    <td key={c.name}>
                      <Cell column={c} row={item} view={view} />
                    </td>
                  ))}
                  <td className="table__actions" onClick={(e) => e.stopPropagation()}>
                    {canEdit && (
                      <>
                        <IconButton icon="edit" label={t('Modifica')} small className="btn--ghost" onClick={() => setEditing(item)} />
                        <IconButton icon="trash" label={t('Elimina')} small danger className="btn--ghost" onClick={() => remove(item)} />
                      </>
                    )}
                  </td>
                </tr>
              ))}
              {data.items.length === 0 && (
                <tr>
                  <td colSpan={columns.length + (canEdit ? 2 : 1)} className="muted table__none">{t('Nessun risultato con questi filtri.')}</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {data && data.total > LIMIT && (
        <div className="pager">
          <IconButton icon="prev" label={t('Pagina precedente')} small className="btn--ghost" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - LIMIT))} />
          <span>
            {offset + 1}–{Math.min(offset + LIMIT, data.total)} di {data.total}
          </span>
          <IconButton icon="next" label={t('Pagina successiva')} small className="btn--ghost" disabled={offset + LIMIT >= data.total} onClick={() => setOffset(offset + LIMIT)} />
        </div>
      )}

      {editing && (
        <ResourceForm resourceKey={resourceKey} item={editing === 'new' ? null : editing} onClose={() => setEditing(null)} onSaved={saved} />
      )}

      {deleting && (
        <DeleteDialog resourceKey={resourceKey} items={deleting} onClose={() => setDeleting(null)}
          note={resourceKey === 'devices' ? t('Vengono eliminate anche le porte e i cavi collegati.') : null}
          onDone={(result) => { setDeleting(null); bulkDone(result) }} />
      )}
      {bulkEditing && (
        <BulkEditDialog resourceKey={resourceKey} items={[...selected.values()]} onClose={() => setBulkEditing(false)} onDone={bulkDone} />
      )}

      {importing && (
        <DeviceImportDialog
          onClose={() => setImporting(false)}
          onImported={() => {
            invalidate()
            reload()
          }}
        />
      )}
    </div>
  )
}

