import { useEffect, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { api, qs } from '../api'
import { useAuth } from '../auth'
import { Badge, ErrorBox, Loading, Mono } from '../components/Bits'
import BulkEditDialog from '../components/BulkEditDialog'
import DeviceImportDialog from '../components/DeviceImportDialog'
import { IconButton } from '../components/Icon'
import RefLabel from '../components/RefLabel'
import { RefSelect } from '../components/RefSelect'
import ResourceForm from '../components/ResourceForm'
import { invalidate, useApi, useDebounced } from '../hooks'
import { labelOf } from '../options'
import { resources } from '../resources'

const LIMIT = 50

function Cell({ column, row }) {
  if (column.render) return column.render(row)
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
      return value ? 'Sì' : 'No'
    case 'color':
      return <span className="swatch" style={{ background: value }} title={value} />
    default:
      return value ?? <span className="muted">—</span>
  }
}

function Filter({ filter, value, onChange }) {
  if (filter.ref) {
    return (
      <RefSelect resource={filter.ref} value={value} onChange={onChange} emptyLabel={`${filter.label}: tutti`} ariaLabel={filter.label} />
    )
  }
  return (
    <select className="input" value={value} onChange={(e) => onChange(e.target.value)} aria-label={filter.label}>
      <option value="">{filter.label}: tutti</option>
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
  const [params] = useSearchParams()
  const [search, setSearch] = useState('')
  // Filtri iniziali dall'indirizzo, es. /devices?reachable=false
  const [filters, setFilters] = useState(() =>
    Object.fromEntries((config.filters || []).filter((f) => params.get(f.name)).map((f) => [f.name, params.get(f.name)])),
  )
  const [offset, setOffset] = useState(0)
  const [editing, setEditing] = useState(null) // null | 'new' | elemento
  const [importing, setImporting] = useState(false)
  const [selected, setSelected] = useState(() => new Map()) // id -> elemento, solo nella pagina visibile
  const [bulkEditing, setBulkEditing] = useState(false)
  const [bulkBusy, setBulkBusy] = useState(null) // "Elimino 3 di 10…"
  const [bulkResult, setBulkResult] = useState(null) // { done, failed: [{ label, error }], verb }
  const q = useDebounced(search)

  const { data, error, loading, reload } = useApi(`/${config.path}${qs({ limit: LIMIT, offset, q, ...filters })}`)
  const filtered = Boolean(q) || Object.values(filters).some((v) => v !== '' && v !== undefined)

  const open = (item) => (config.detail ? navigate(config.detail(item)) : setEditing(item))

  // Cambiando pagina, ricerca o filtri la selezione riparte da zero
  useEffect(() => setSelected(new Map()), [q, filters, offset])
  const items = data?.items || []
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
    if (!window.confirm(`Eliminare ${chosen.length === 1 ? '1 elemento' : `${chosen.length} elementi`}? Non si può annullare.`)) return
    const failed = []
    for (let i = 0; i < chosen.length; i++) {
      setBulkBusy(`Elimino ${i + 1} di ${chosen.length}…`)
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
      const url = `/api/devices/export${qs({ format, q, ...filters })}`
      const res = await fetch(url)
      if (!res.ok) throw new Error("Errore durante l'esportazione dei device")
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
    if (!window.confirm(`Eliminare "${config.label(item)}"?`)) return
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
              <IconButton icon="download" label="Esporta in CSV (si apre con Excel), con i filtri attivi" onClick={() => handleExport('csv')}>
                <span className="btn__tag">CSV</span>
              </IconButton>
              <IconButton icon="download" label="Esporta in JSON, con i filtri attivi" onClick={() => handleExport('json')}>
                <span className="btn__tag">JSON</span>
              </IconButton>
              {canEdit && <IconButton icon="upload" label="Importa device da un file CSV" onClick={() => setImporting(true)} />}
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
          placeholder="Cerca"
          value={search}
          aria-label={`Cerca in ${config.title}`}
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
            onChange={(v) => {
              setFilters((prev) => ({ ...prev, [f.name]: v }))
              setOffset(0)
            }}
          />
        ))}
        {data && <span className="toolbar__count">{data.total === 1 ? '1 elemento' : `${data.total} elementi`}</span>}
      </div>

      {canEdit && selected.size > 0 && (
        <div className="bulk-bar" role="region" aria-label="Elementi selezionati">
          <strong>{selected.size === 1 ? '1 selezionato' : `${selected.size} selezionati`}</strong>
          {bulkBusy ? (
            <span className="muted">{bulkBusy}</span>
          ) : (
            <>
              {config.bulkFields && (
                <IconButton icon="edit" label="Modifica i selezionati" small onClick={() => setBulkEditing(true)} />
              )}
              <IconButton icon="trash" label="Elimina i selezionati" small danger onClick={removeSelected} />
              <IconButton icon="close" label="Togli la selezione" small className="btn--ghost" onClick={() => toggleAll(false)} />
            </>
          )}
        </div>
      )}
      {bulkResult && (
        <div className={`notice${bulkResult.failed.length ? ' notice--warn' : ''}`} role="status">
          {bulkResult.done === 1 ? '1 elemento' : `${bulkResult.done} elementi`} {bulkResult.verb}.
          {bulkResult.failed.length > 0 && (
            <>
              {' '}Non riusciti:
              <ul>
                {bulkResult.failed.map((f) => <li key={f.label}>{f.label}: {f.error}</li>)}
              </ul>
            </>
          )}
          <IconButton icon="close" label="Chiudi il messaggio" small className="btn--ghost notice__close" onClick={() => setBulkResult(null)} />
        </div>
      )}

      <ErrorBox error={error} />
      {!data && loading && <Loading />}

      {data && data.items.length === 0 && (
        <div className="empty">
          {filtered ? (
            <p>Nessun risultato con questi filtri.</p>
          ) : (
            <>
              <p>Non c'è ancora niente qui.</p>
              {canEdit && (
                <IconButton icon="plus" label={config.newLabel} className="btn--primary" onClick={() => setEditing('new')} />
              )}
            </>
          )}
        </div>
      )}

      {data && data.items.length > 0 && (
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                {canEdit && (
                  <th className="table__select">
                    <input type="checkbox" checked={allSelected} aria-label="Seleziona tutti quelli della pagina"
                      onChange={(e) => toggleAll(e.target.checked)} />
                  </th>
                )}
                {config.columns.map((c) => (
                  <th key={c.name}>{c.label}</th>
                ))}
                <th className="table__actions">
                  <span className="sr-only">Azioni</span>
                </th>
              </tr>
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
                  {config.columns.map((c) => (
                    <td key={c.name}>
                      <Cell column={c} row={item} />
                    </td>
                  ))}
                  <td className="table__actions" onClick={(e) => e.stopPropagation()}>
                    {canEdit && (
                      <>
                        <IconButton icon="edit" label="Modifica" small className="btn--ghost" onClick={() => setEditing(item)} />
                        <IconButton icon="trash" label="Elimina" small danger className="btn--ghost" onClick={() => remove(item)} />
                      </>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {data && data.total > LIMIT && (
        <div className="pager">
          <IconButton icon="prev" label="Pagina precedente" small className="btn--ghost" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - LIMIT))} />
          <span>
            {offset + 1}–{Math.min(offset + LIMIT, data.total)} di {data.total}
          </span>
          <IconButton icon="next" label="Pagina successiva" small className="btn--ghost" disabled={offset + LIMIT >= data.total} onClick={() => setOffset(offset + LIMIT)} />
        </div>
      )}

      {editing && (
        <ResourceForm resourceKey={resourceKey} item={editing === 'new' ? null : editing} onClose={() => setEditing(null)} onSaved={saved} />
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

