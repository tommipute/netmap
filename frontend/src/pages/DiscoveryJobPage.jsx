import { Fragment, useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api } from '../api'
import { Badge, ErrorBox, Loading, Mono } from '../components/Bits'
import RefLabel from '../components/RefLabel'
import ResourceForm from '../components/ResourceForm'
import { invalidate, useApi, useOptions } from '../hooks'
import { RUN_STATUS, formatDateTime, formatDuration } from '../options'

const RUN_TONE = { queued: 'muted', running: 'info', done: 'ok', failed: 'danger' }

function RunStatus({ status }) {
  const label = RUN_STATUS.find((o) => o.value === status)?.label ?? status
  return <span className={`badge badge--${RUN_TONE[status] || 'muted'}`}>{label}</span>
}

export default function DiscoveryJobPage() {
  const { id } = useParams()
  const navigate = useNavigate()
  const { data: job, error, reload } = useApi(`/discovery-jobs/${id}`)
  const { data: runs, reload: reloadRuns } = useApi(`/discovery-runs?job_id=${id}&limit=20`)
  const { data: pending, reload: reloadPending } = useApi(`/discovery-changes?job_id=${id}&limit=1`)
  const profiles = useOptions('snmp-profiles')
  const [editing, setEditing] = useState(false)
  const [openLog, setOpenLog] = useState(null)
  const [actionError, setActionError] = useState(null)

  const active = runs?.items.some((r) => r.status === 'queued' || r.status === 'running')

  // Mentre una scansione è in coda o in corso, aggiorno lo storico ogni 2 secondi
  useEffect(() => {
    if (!active) return undefined
    const timer = setInterval(() => {
      reloadRuns()
      reloadPending()
    }, 2000)
    return () => {
      clearInterval(timer)
      reloadPending()
      invalidate() // a scansione finita aggiorna anche il contatore nel menu
    }
  }, [active, reloadRuns, reloadPending])

  const start = async () => {
    setActionError(null)
    try {
      const run = await api.post(`/discovery-jobs/${id}/run`)
      setOpenLog(run.id)
      reloadRuns()
    } catch (err) {
      setActionError(err)
    }
  }

  const remove = async () => {
    if (!window.confirm(`Eliminare la scansione "${job.name}"? Vengono eliminati anche lo storico e le modifiche in attesa.`)) return
    try {
      await api.del(`/discovery-jobs/${id}`)
      invalidate()
      navigate('/discovery-jobs')
    } catch (err) {
      setActionError(err)
    }
  }

  if (error) return <div className="page"><ErrorBox error={error} /></div>
  if (!job) return <div className="page"><Loading /></div>

  const profileNames = job.profile_ids.map((pid) => profiles.find((p) => p.id === pid)?.name ?? `#${pid}`)

  return (
    <div className="page">
      <header className="page-head">
        <div>
          <p className="crumbs"><Link to="/discovery-jobs">Scansioni</Link></p>
          <h1 className="device-title">
            {job.name}
            {!job.enabled && <span className="badge badge--muted">Disattivata</span>}
          </h1>
          {job.description && <p className="page-intro">{job.description}</p>}
        </div>
        <div className="page-head__actions">
          <button type="button" className="btn btn--primary" onClick={start} disabled={active}>
            {active ? 'Scansione in corso…' : 'Avvia scansione'}
          </button>
          <button type="button" className="btn" onClick={() => setEditing(true)}>Modifica</button>
          <button type="button" className="btn btn--ghost btn--danger" onClick={remove}>Elimina</button>
        </div>
      </header>

      <ErrorBox error={actionError} />

      {pending?.total > 0 && (
        <p className="notice">
          Questa scansione ha {pending.total === 1 ? '1 modifica' : `${pending.total} modifiche`} da approvare.{' '}
          <Link to={`/discovery/changes?job_id=${id}`}>Rivedile</Link>
        </p>
      )}

      <dl className="facts">
        <div className="facts__wide"><dt>Indirizzi</dt><dd><Mono>{job.targets.join(', ')}</Mono></dd></div>
        <div><dt>Profili, in ordine</dt><dd>{profileNames.join(', ')}</dd></div>
        <div><dt>Sede dei device nuovi</dt><dd><RefLabel resource="sites" id={job.site_id} /></dd></div>
        <div><dt>Quando</dt><dd>{job.interval_hours ? `Ogni ${job.interval_hours} ore` : 'Solo a mano'}</dd></div>
        <div>
          <dt>Applica da sola</dt>
          <dd>
            {[job.auto_new_interfaces && 'porte nuove', job.auto_new_ips && 'IP nuovi'].filter(Boolean).join(', ') || 'Niente: approvi tutto tu'}
          </dd>
        </div>
      </dl>

      <section className="section">
        <header className="section__head">
          <h2>
            Esecuzioni
            {runs && <span className="section__count">ultime {runs.items.length} di {runs.total}</span>}
          </h2>
        </header>
        {runs && runs.items.length === 0 && (
          <div className="empty"><p>Non è ancora stata eseguita. Premi "Avvia scansione" per provarla.</p></div>
        )}
        {runs && runs.items.length > 0 && (
          <div className="table-wrap">
            <table className="table table--dense">
              <thead>
                <tr>
                  <th>Avviata</th>
                  <th>Stato</th>
                  <th>Durata</th>
                  <th>Host che hanno risposto</th>
                  <th>Da approvare</th>
                  <th>Applicate da sola</th>
                  <th className="table__actions"><span className="sr-only">Log</span></th>
                </tr>
              </thead>
              <tbody>
                {runs.items.map((run) => (
                  <Fragment key={run.id}>
                    <tr>
                      <td>{formatDateTime(run.started_at || run.requested_at)}</td>
                      <td><RunStatus status={run.status} /></td>
                      <td>{formatDuration(run.started_at, run.finished_at)}</td>
                      <td>{run.status === 'queued' ? '—' : `${run.hosts_responded} su ${run.hosts_total}`}</td>
                      <td>{run.changes_proposed}</td>
                      <td>{run.changes_applied}</td>
                      <td className="table__actions">
                        <button type="button" className="btn btn--ghost btn--sm" aria-expanded={openLog === run.id}
                          onClick={() => setOpenLog(openLog === run.id ? null : run.id)}>
                          {openLog === run.id ? 'Nascondi log' : 'Log'}
                        </button>
                      </td>
                    </tr>
                    {openLog === run.id && (
                      <tr>
                        <td colSpan={7}>
                          <pre className="log">{run.log || (run.status === 'queued' ? 'In attesa del worker…' : 'Nessun messaggio.')}</pre>
                        </td>
                      </tr>
                    )}
                  </Fragment>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {editing && (
        <ResourceForm
          resourceKey="discovery-jobs"
          item={job}
          onClose={() => setEditing(false)}
          onSaved={() => {
            setEditing(false)
            reload()
          }}
        />
      )}
    </div>
  )
}
