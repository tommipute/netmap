import { Fragment, useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api } from '../api'
import { useAuth } from '../auth'
import { Badge, ErrorBox, Loading, Mono } from '../components/Bits'
import { IconButton } from '../components/Icon'
import ProbeDialog, { PROBE_MAX_HOSTS } from '../components/ProbeDialog'
import RefLabel from '../components/RefLabel'
import ResourceForm from '../components/ResourceForm'
import { invalidate, useApi, useOptions } from '../hooks'
import { RUN_STATUS, formatDateTime, formatDuration } from '../options'
import { t, tn, tServer } from '../i18n'
import { parseTarget } from '../targets'

const RUN_TONE = { queued: 'muted', running: 'info', done: 'ok', failed: 'danger' }

function RunStatus({ status }) {
  const label = RUN_STATUS.find((o) => o.value === status)?.label ?? status
  return <span className={`badge badge--${RUN_TONE[status] || 'muted'}`}>{label}</span>
}

export default function DiscoveryJobPage() {
  const { canEdit } = useAuth()
  const { id } = useParams()
  const navigate = useNavigate()
  const { data: job, error, reload } = useApi(`/discovery-jobs/${id}`)
  const { data: runs, reload: reloadRuns } = useApi(`/discovery-runs?job_id=${id}&limit=20`)
  const { data: pending, reload: reloadPending } = useApi(`/discovery-changes?job_id=${id}&limit=1`)
  const profiles = useOptions('snmp-profiles')
  const [editing, setEditing] = useState(false)
  const [probing, setProbing] = useState(false)
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
    if (!window.confirm(t('Eliminare la scansione "{name}"? Vengono eliminati anche lo storico e le modifiche in attesa.', { name: job.name }))) return
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
          <p className="crumbs"><Link to="/discovery-jobs">{t('Scansioni')}</Link></p>
          <h1 className="device-title">
            {job.name}
            {!job.enabled && <span className="badge badge--muted">{t('Disattivata')}</span>}
          </h1>
          {job.description && <p className="page-intro">{job.description}</p>}
        </div>
        <div className="page-head__actions">
          {canEdit && (
            <>
              <IconButton icon={active ? 'refresh' : 'play'} label={active ? t('Scansione in corso…') : t('Avvia scansione')}
                className={`btn--primary${active ? ' is-spinning' : ''}`} onClick={start} disabled={active} />
              <IconButton icon="search" label={t('Prova indirizzi: cosa succede su ognuno, senza salvare niente')} onClick={() => setProbing(true)} />
              <IconButton icon="edit" label={t('Modifica scansione')} onClick={() => setEditing(true)} />
              <IconButton icon="trash" label={t('Elimina scansione')} danger className="btn--ghost" onClick={remove} />
            </>
          )}
        </div>
      </header>

      <ErrorBox error={actionError} />

      {pending?.total > 0 && (
        <p className="notice">
          {tn(pending.total, 'Questa scansione ha 1 modifica da approvare.', 'Questa scansione ha {n} modifiche da approvare.')}{' '}
          <Link to={`/discovery/changes?job_id=${id}`}>{t('Rivedile')}</Link>
        </p>
      )}

      <dl className="facts">
        <div className="facts__wide"><dt>{t('Indirizzi')}</dt><dd><Mono>{job.targets.join(', ')}</Mono></dd></div>
        <div><dt>{t('Profili, in ordine')}</dt><dd>{profileNames.join(', ')}</dd></div>
        <div><dt>{t('Sede dei device nuovi')}</dt><dd><RefLabel resource="sites" id={job.site_id} /></dd></div>
        <div><dt>{t('Quando')}</dt><dd>{job.interval_hours ? t('Ogni {n} ore', { n: job.interval_hours }) : t('Solo a mano')}</dd></div>
        <div>
          <dt>{t('Applica da sola')}</dt>
          <dd>
            {[job.auto_new_interfaces && t('porte nuove'), job.auto_new_ips && t('IP nuovi')].filter(Boolean).join(', ') || t('Niente: approvi tutto tu')}
          </dd>
        </div>
      </dl>

      <section className="section">
        <header className="section__head">
          <h2>
            {t('Esecuzioni')}
            {runs && <span className="section__count">{t('ultime {n} di {total}', { n: runs.items.length, total: runs.total })}</span>}
          </h2>
        </header>
        {runs && runs.items.length === 0 && (
          <div className="empty"><p>{t('Non è ancora stata eseguita. Premi "Avvia scansione" per provarla.')}</p></div>
        )}
        {runs && runs.items.length > 0 && (
          <div className="table-wrap">
            <table className="table table--dense">
              <thead>
                <tr>
                  <th>{t('Avviata')}</th>
                  <th>{t('Stato')}</th>
                  <th>{t('Durata')}</th>
                  <th>{t('Host che hanno risposto')}</th>
                  <th>{t('Da approvare')}</th>
                  <th>{t('Applicate da sola')}</th>
                  <th className="table__actions"><span className="sr-only">{t('Log')}</span></th>
                </tr>
              </thead>
              <tbody>
                {runs.items.map((run) => (
                  <Fragment key={run.id}>
                    <tr>
                      <td>{formatDateTime(run.started_at || run.requested_at)}</td>
                      <td><RunStatus status={run.status} /></td>
                      <td>{formatDuration(run.started_at, run.finished_at)}</td>
                      <td>{run.status === 'queued' ? '—' : t('{n} su {total}', { n: run.hosts_responded, total: run.hosts_total })}</td>
                      <td>{run.changes_proposed}</td>
                      <td>{run.changes_applied}</td>
                      <td className="table__actions">
                        <IconButton icon="log" label={openLog === run.id ? t('Nascondi log') : t('Mostra log')} small
                          className={openLog === run.id ? 'btn--ghost is-on' : 'btn--ghost'} aria-expanded={openLog === run.id}
                          onClick={() => setOpenLog(openLog === run.id ? null : run.id)} />
                      </td>
                    </tr>
                    {openLog === run.id && (
                      <tr>
                        <td colSpan={7}>
                          <pre className="log">{tServer(run.log) || (run.status === 'queued' ? t('In attesa del worker…') : t('Nessun messaggio.'))}</pre>
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

      {probing && (
        <ProbeDialog
          onClose={() => setProbing(false)}
          profileIds={job.profile_ids}
          // gli indirizzi della scansione, se sono pochi abbastanza
          targets={job.targets.reduce((n, x) => n + (parseTarget(x).count ?? Infinity), 0) <= PROBE_MAX_HOSTS ? job.targets : []}
        />
      )}

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
