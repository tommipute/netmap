import { useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { api, qs } from '../api'
import { useAuth } from '../auth'
import { ErrorBox, Loading } from '../components/Bits'
import { RefSelect } from '../components/RefSelect'
import { invalidate, useApi } from '../hooks'
import { CHANGE_ACTIONS, CHANGE_STATUS, formatDateTime } from '../options'

const OBJECT_LABELS = { device: 'Device', interface: 'Porta', ip: 'IP', cable: 'Cavo' }

function show(value) {
  if (value === null || value === undefined || value === '') return <span className="muted">—</span>
  if (value === true) return 'Sì'
  if (value === false) return 'No'
  return String(value)
}

function Diff({ diff }) {
  const rows = diff || [] // [campo, attuale, proposto]
  if (rows.length === 0) return null
  const isNew = rows.every(([, before]) => before === null || before === undefined)
  return (
    <table className="diff">
      <tbody>
        {rows.map(([field, before, after]) => (
          <tr key={field}>
            <th scope="row">{field}</th>
            {!isNew && <td className="diff__old">{show(before)}</td>}
            {!isNew && <td className="diff__arrow" aria-hidden="true">→</td>}
            <td className="diff__new">{show(after)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

function ChangeRow({ change, busy, onDecide }) {
  const { canEdit } = useAuth()
  const action = CHANGE_ACTIONS[change.action] || { label: change.action, tone: 'muted' }
  const pending = change.status === 'pending'
  return (
    <li className="change">
      <div className="change__main">
        <p className="change__title">
          <span className={`badge badge--${action.tone}`}>{action.label}</span>
          <span className="change__kind">{OBJECT_LABELS[change.object_type] || change.object_type}</span>
          {change.summary}
        </p>
        <Diff diff={change.diff} />
        {change.error && <p className="change__error">{change.error}</p>}
        {!pending && (
          <p className="hint">
            {change.auto ? 'Applicata in automatico' : CHANGE_STATUS.find((s) => s.value === change.status)?.label}
            {change.decided_at && `, ${formatDateTime(change.decided_at)}`}
          </p>
        )}
      </div>
      {pending && canEdit && (
        <div className="change__actions">
          <button type="button" className="btn btn--sm btn--primary" disabled={busy} onClick={() => onDecide('approve', [change.id])}>
            Approva
          </button>
          <button type="button" className="btn btn--sm btn--ghost" disabled={busy} onClick={() => onDecide('reject', [change.id])}>
            Rifiuta
          </button>
        </div>
      )}
    </li>
  )
}

export default function ChangesPage() {
  const { canEdit } = useAuth()
  const [params, setParams] = useSearchParams()
  const status = params.get('status') || 'pending'
  const jobId = params.get('job_id') ? Number(params.get('job_id')) : ''
  const deviceId = params.get('device_id') ? Number(params.get('device_id')) : ''
  const { data, error, loading, reload } = useApi(
    `/discovery-changes${qs({ status, job_id: jobId, device_id: deviceId, limit: status === 'pending' ? 5000 : 300 })}`,
  )
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState(null)

  const setFilter = (key, value) => {
    const next = new URLSearchParams(params)
    if (value === '' || value === null || value === undefined) next.delete(key)
    else next.set(key, value)
    setParams(next, { replace: true })
    setResult(null)
  }

  // Raggruppate per device (anche i device nuovi, per nome)
  const groups = useMemo(() => {
    const map = new Map()
    for (const change of data?.items || []) {
      const key = change.device_label
      if (!map.has(key)) map.set(key, { label: key, deviceId: change.device_id, items: [] })
      map.get(key).items.push(change)
    }
    return [...map.values()]
  }, [data])

  const decide = async (kind, ids) => {
    if (kind === 'reject' && ids.length > 1 && !window.confirm(`Rifiutare ${ids.length} modifiche? Con gli stessi dati non verranno riproposte.`)) return
    setBusy(true)
    setResult(null)
    try {
      const response = await api.post(`/discovery-changes/${kind}`, { ids })
      setResult(kind === 'approve' ? response : { rejected: response.rejected })
      invalidate()
      reload()
    } catch (err) {
      setResult({ error: err.message })
    } finally {
      setBusy(false)
    }
  }

  const allIds = (data?.items || []).map((c) => c.id)
  const pendingView = status === 'pending'

  return (
    <div className="page">
      <header className="page-head">
        <div>
          <h1>Da approvare</h1>
          <p className="page-intro">
            Quello che le scansioni SNMP hanno trovato di nuovo o di diverso. Niente cambia finché non lo approvi;
            una modifica rifiutata non viene riproposta finché i dati restano uguali.
          </p>
        </div>
        {canEdit && pendingView && allIds.length > 0 && (
          <div className="page-head__actions">
            <button type="button" className="btn btn--primary" disabled={busy} onClick={() => decide('approve', allIds)}>
              Approva tutte ({allIds.length})
            </button>
          </div>
        )}
      </header>

      <div className="toolbar">
        <div className="segmented" role="tablist" aria-label="Stato">
          {CHANGE_STATUS.map((s) => (
            <button key={s.value} type="button" role="tab" aria-selected={status === s.value}
              className={`segmented__item${status === s.value ? ' segmented__item--on' : ''}`}
              onClick={() => setFilter('status', s.value === 'pending' ? '' : s.value)}>
              {s.label}
            </button>
          ))}
        </div>
        <RefSelect resource="discovery-jobs" value={jobId} onChange={(v) => setFilter('job_id', v)} emptyLabel="Tutte le scansioni" ariaLabel="Scansione" />
        {deviceId && (
          <button type="button" className="btn btn--ghost btn--sm" onClick={() => setFilter('device_id', '')}>
            Mostra tutti i device
          </button>
        )}
        {data && <span className="toolbar__count">{data.total === 1 ? '1 modifica' : `${data.total} modifiche`}</span>}
      </div>

      {result && !result.error && (
        <div className={`notice${result.failed?.length ? ' notice--warn' : ''}`} role="status">
          {result.rejected !== undefined
            ? `${result.rejected === 1 ? '1 modifica rifiutata' : `${result.rejected} modifiche rifiutate`}.`
            : `${result.applied === 1 ? '1 modifica applicata' : `${result.applied} modifiche applicate`}.`}
          {result.failed?.length > 0 && (
            <>
              {' '}Non applicate perché nel frattempo i dati sono cambiati:
              <ul>
                {result.failed.map((f) => (
                  <li key={f.id}>{f.summary}: {f.error}</li>
                ))}
              </ul>
            </>
          )}
        </div>
      )}
      <ErrorBox error={result?.error ? { message: result.error } : error} />
      {!data && loading && <Loading />}

      {data && data.items.length === 0 && (
        <div className="empty">
          {pendingView ? (
            <p>
              Niente da approvare. Le modifiche compaiono qui dopo una <Link to="/discovery-jobs">scansione</Link>.
            </p>
          ) : (
            <p>Nessuna modifica in questo elenco.</p>
          )}
        </div>
      )}

      {groups.map((group) => (
        <section key={group.label} className="section change-group">
          <header className="section__head">
            <h2>
              {group.deviceId ? <Link to={`/devices/${group.deviceId}`}>{group.label}</Link> : group.label}
              <span className="section__count">
                {group.items.length === 1 ? '1 modifica' : `${group.items.length} modifiche`}
              </span>
            </h2>
            {canEdit && pendingView && group.items.length > 1 && (
              <div className="page-head__actions">
                <button type="button" className="btn btn--sm" disabled={busy} onClick={() => decide('approve', group.items.map((c) => c.id))}>
                  Approva tutte
                </button>
                <button type="button" className="btn btn--sm btn--ghost" disabled={busy} onClick={() => decide('reject', group.items.map((c) => c.id))}>
                  Rifiuta tutte
                </button>
              </div>
            )}
          </header>
          <ul className="changes">
            {group.items.map((change) => (
              <ChangeRow key={change.id} change={change} busy={busy} onDecide={decide} />
            ))}
          </ul>
        </section>
      ))}
    </div>
  )
}
