import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api } from '../api'
import { useAuth } from '../auth'
import { ErrorBox, LiveStatus, Loading, PrintFooter } from '../components/Bits'
import { IconButton } from '../components/Icon'
import RefLabel from '../components/RefLabel'
import ResourceForm from '../components/ResourceForm'
import { invalidate, useApi } from '../hooks'

const UNIT_PX = 26

/** Vista frontale: U numerate dal basso, device alti quanto il loro modello. */
function Elevation({ view }) {
  const units = Array.from({ length: view.u_height }, (_, i) => view.u_height - i)
  return (
    <div className="rack" style={{ '--units': view.u_height, '--unit': `${UNIT_PX}px` }} role="img"
      aria-label={`Rack ${view.name}, ${view.u_height} unità, ${view.used_units} occupate`}>
      <ol className="rack__scale" aria-hidden="true">
        {units.map((u) => <li key={u}>{u}</li>)}
      </ol>
      <div className="rack__bay">
        {units.map((u) => <div key={u} className="rack__slot" style={{ gridRow: view.u_height - u + 1 }} />)}
        {view.devices.map((d) => {
          if (d.position > view.u_height) return null
          // Righe della griglia dall'alto: l'unità u sta nella riga (altezza - u + 1)
          const bottom = view.u_height - d.position + 1
          const top = Math.max(1, bottom - d.u_height + 1)
          const span = bottom - top + 1
          return (
            <Link key={d.id} to={`/devices/${d.id}`}
              className={`rack__device${d.conflict ? ' rack__device--conflict' : ''}${d.status !== 'active' ? ' rack__device--inactive' : ''}`}
              style={{ gridRow: `${top} / span ${span}`, '--role': d.color }}
              title={`${d.name} · U${d.position}${d.u_height > 1 ? `–${d.position + d.u_height - 1}` : ''}${d.conflict ? ' · si sovrappone a un altro device' : ''}`}>
              {d.reachable !== null && <span className={`live-dot live-dot--${d.reachable ? 'up' : 'down'}`} />}
              <span className="rack__name">{d.name}</span>
              {d.face_label && span > 1 && <span className="rack__model">{d.face_label}</span>}
            </Link>
          )
        })}
      </div>
    </div>
  )
}

export default function RackPage() {
  const { id } = useParams()
  const navigate = useNavigate()
  const { canEdit } = useAuth()
  const { data: rack, error, reload } = useApi(`/racks/${id}`)
  const { data: view, error: viewError, reload: reloadView } = useApi(`/racks/${id}/elevation`)
  const [editing, setEditing] = useState(false)

  const remove = async () => {
    if (!window.confirm(`Eliminare il rack ${rack.name}? I device restano, senza rack.`)) return
    try {
      await api.del(`/racks/${id}`)
      invalidate()
      navigate('/racks')
    } catch (err) {
      window.alert(err.message)
    }
  }

  if (error) return <div className="page"><ErrorBox error={error} /></div>
  if (!rack) return <div className="page"><Loading /></div>

  const outside = view?.devices.filter((d) => d.position > view.u_height) ?? []
  const conflicts = view?.devices.filter((d) => d.conflict) ?? []

  return (
    <div className="page">
      <header className="page-head">
        <div>
          <p className="crumbs"><Link to="/racks">Rack</Link></p>
          <h1>{rack.name}</h1>
          <p className="page-intro">
            <RefLabel resource="sites" id={rack.site_id} />
            {rack.location_id && <>, <RefLabel resource="locations" id={rack.location_id} /></>}
            {view && ` · ${view.used_units} di ${view.u_height} U occupate`}
          </p>
        </div>
        <div className="page-head__actions">
          <IconButton icon="print" label="Stampa il rack" onClick={() => window.print()} />
          {canEdit && <IconButton icon="edit" label="Modifica rack" onClick={() => setEditing(true)} />}
          {canEdit && <IconButton icon="trash" label="Elimina rack" danger className="btn--ghost" onClick={remove} />}
        </div>
      </header>

      <ErrorBox error={viewError} />
      {conflicts.length > 0 && (
        <p className="notice notice--warn">
          Alcuni device si sovrappongono o escono dal rack: {conflicts.map((d) => d.name).join(', ')}. Controlla unità e modello.
        </p>
      )}

      {view && (
        <div className="rack-layout">
          <Elevation view={view} />
          <div className="rack-side">
            <section className="section">
              <h2>Nel rack senza unità</h2>
              {view.unplaced.length === 0 && outside.length === 0 ? (
                <p className="muted">Nessuno: tutti i device hanno la loro posizione.</p>
              ) : (
                <ul className="results">
                  {[...view.unplaced, ...outside].map((d) => (
                    <li key={d.id}>
                      <Link to={`/devices/${d.id}`}>{d.name}</Link>
                      <span className="results__detail">
                        {d.position ? `U${d.position}: oltre l'altezza del rack` : 'manca l\'unità'}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </section>
            <section className="section">
              <h2>Device</h2>
              {view.devices.length === 0 ? (
                <p className="muted">Nessun device ha questo rack. Assegnalo dalla scheda del device (campo Rack e Unità).</p>
              ) : (
                <ul className="results">
                  {[...view.devices].sort((a, b) => b.position - a.position).map((d) => (
                    <li key={d.id}>
                      <span className="mono">U{d.position}</span>
                      <Link to={`/devices/${d.id}`}>{d.name}</Link>
                      <span className="results__detail">{d.face_label || d.role || ''}</span>
                      <LiveStatus device={d} />
                    </li>
                  ))}
                </ul>
              )}
            </section>
          </div>
        </div>
      )}

      <PrintFooter />

      {editing && (
        <ResourceForm resourceKey="racks" item={rack} onClose={() => setEditing(false)}
          onSaved={() => { setEditing(false); reload(); reloadView() }} />
      )}
    </div>
  )
}
