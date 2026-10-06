import { useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { api, qs } from '../api'
import { useAuth } from '../auth'
import { Badge, ErrorBox, Loading, Mono } from '../components/Bits'
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
  const q = useDebounced(search)

  const { data, error, loading, reload } = useApi(`/${config.path}${qs({ limit: LIMIT, offset, q, ...filters })}`)
  const filtered = Boolean(q) || Object.values(filters).some((v) => v !== '' && v !== undefined)

  const open = (item) => (config.detail ? navigate(config.detail(item)) : setEditing(item))

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
                  className="table__row--link"
                  tabIndex={0}
                  onClick={() => (config.detail || canEdit) && open(item)}
                  onKeyDown={(e) => e.key === 'Enter' && e.target === e.currentTarget && (config.detail || canEdit) && open(item)}
                >
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

