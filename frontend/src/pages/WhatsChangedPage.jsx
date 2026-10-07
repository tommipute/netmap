import { Link, useSearchParams } from 'react-router-dom'
import { qs } from '../api'
import { ErrorBox, Loading, Mono } from '../components/Bits'
import HistoryList, { SOURCES } from '../components/HistoryList'
import { useApi } from '../hooks'
import { formatDateTime, formatSince } from '../options'

const PERIODS = [
  { hours: 24, label: 'Ultime 24 ore' },
  { hours: 24 * 7, label: 'Ultimi 7 giorni' },
  { hours: 24 * 30, label: 'Ultimi 30 giorni' },
]

function Tile({ value, label, detail, to, tone }) {
  const body = (
    <>
      <span className="tile__value">{value}</span>
      <span className="tile__label">{label}</span>
      {detail && <span className="tile__detail">{detail}</span>}
    </>
  )
  const className = `tile${tone && value ? ` tile--${tone}` : ''}`
  return to ? <Link to={to} className={className}>{body}</Link> : <div className={className}>{body}</div>
}

function DeviceList({ items, empty, render }) {
  if (items.length === 0) return <p className="muted">{empty}</p>
  return (
    <ul className="plain-list">
      {items.map((d) => (
        <li key={`${d.id}-${d.at}`}>{render(d)}</li>
      ))}
    </ul>
  )
}

function EndpointTable({ items, moved }) {
  return (
    <div className="table-wrap">
      <table className="table table--dense">
        <thead>
          <tr>
            <th>MAC</th>
            <th>IP</th>
            <th>{moved ? 'Adesso su' : 'Switch e porta'}</th>
            {moved && <th>Prima su</th>}
            <th>VLAN</th>
            <th>{moved ? 'Spostato' : 'Visto la prima volta'}</th>
          </tr>
        </thead>
        <tbody>
          {items.map((e) => (
            <tr key={e.id}>
              <td>
                <Link to={`/where?q=${encodeURIComponent(e.mac)}`}><Mono>{e.mac}</Mono></Link>
                {e.known_as && <div className="hint">{e.known_as}</div>}
              </td>
              <td><Mono>{e.ip}</Mono></td>
              <td>
                {e.device_id ? <><Link to={`/devices/${e.device_id}`}>{e.device_name}</Link> <Mono>{e.interface_name}</Mono></> : <span className="muted">porta eliminata</span>}
              </td>
              {moved && <td>{e.previous_device_name ? <>{e.previous_device_name} <Mono>{e.previous_interface_name}</Mono></> : '—'}</td>}
              <td>{e.vlan ? `${e.vlan}${e.vlan_name ? ` ${e.vlan_name}` : ''}` : '—'}</td>
              <td>{formatDateTime(moved ? e.moved_at : e.first_seen_at)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

/** Cosa è cambiato in un periodo: modifiche, device giù o tornati, PC nuovi o spostati, scansioni. */
export default function WhatsChangedPage() {
  const [params, setParams] = useSearchParams()
  const hours = Number(params.get('hours')) || 24
  const { data, error, loading } = useApi(`/whats-changed${qs({ hours })}`)
  const since = data?.since
  const recent = useApi(since ? `/audit-log${qs({ since, limit: 15 })}` : null)

  const sourceText = data
    ? SOURCES.filter((s) => data.changes.by_source[s.value]).map((s) => `${s.label.toLowerCase()} ${data.changes.by_source[s.value]}`).join(', ')
    : ''

  return (
    <div className="page">
      <header className="page-head">
        <div>
          <h1>Cosa è cambiato</h1>
          <p className="page-intro">
            Il riassunto del periodo: modifiche alla documentazione, device che non rispondono, apparecchi nuovi o
            spostati visti dalla scansione.
          </p>
        </div>
      </header>

      <div className="toolbar">
        <div className="segmented" role="group" aria-label="Periodo">
          {PERIODS.map((p) => (
            <button key={p.hours} type="button" className={`segmented__item${p.hours === hours ? ' segmented__item--on' : ''}`}
              aria-pressed={p.hours === hours} onClick={() => setParams({ hours: String(p.hours) }, { replace: true })}>
              {p.label}
            </button>
          ))}
        </div>
        {since && <span className="toolbar__count">dal {formatDateTime(since)}</span>}
      </div>

      <ErrorBox error={error} />
      {!data && loading && <Loading />}
      {data && (
        <>
          <div className="tiles">
            <Tile value={data.devices_down.length} label="Non rispondono" tone="danger"
              detail={data.devices_down.some((d) => d.new) ? `${data.devices_down.filter((d) => d.new).length} nel periodo` : null}
              to="/devices?reachable=false" />
            <Tile value={data.devices_back.length} label="Tornati a rispondere" tone="ok" />
            <Tile value={data.changes.total} label="Modifiche" detail={sourceText || null} to="/history" />
            <Tile value={data.endpoints_new.total} label="Apparecchi nuovi in rete" tone="info" />
            <Tile value={data.endpoints_moved.total} label="Apparecchi spostati" tone="warn" />
            <Tile value={data.runs.total} label="Scansioni"
              detail={data.runs.failed.length ? `${data.runs.failed.length} non riuscite` : null} tone={data.runs.failed.length ? 'danger' : null} to="/discovery-jobs" />
            <Tile value={data.pending_changes} label="Da approvare" tone="warn" to="/discovery/changes" />
          </div>

          <div className="two-cols">
            <section className="section">
              <h2>Non rispondono</h2>
              <DeviceList items={data.devices_down} empty="Tutti i device controllati rispondono."
                render={(d) => (
                  <>
                    <span className="live-dot live-dot--down" /> <Link to={`/devices/${d.id}`}>{d.name}</Link>{' '}
                    <span className="muted">{formatSince(d.at)}</span> {d.new && <span className="tag">nuovo</span>}
                  </>
                )} />
            </section>
            <section className="section">
              <h2>Tornati a rispondere</h2>
              <DeviceList items={data.devices_back} empty="Nessuno nel periodo."
                render={(d) => (
                  <>
                    <span className="live-dot live-dot--up" /> <Link to={`/devices/${d.id}`}>{d.name}</Link>{' '}
                    <span className="muted">{formatDateTime(d.at)}</span>
                  </>
                )} />
            </section>
            <section className="section">
              <h2>Device aggiunti</h2>
              <DeviceList items={data.devices_created} empty="Nessuno nel periodo."
                render={(d) => (
                  <>
                    {d.exists ? <Link to={`/devices/${d.id}`}>{d.name}</Link> : <span className="muted">{d.name} (poi eliminato)</span>}{' '}
                    <span className="muted">{formatDateTime(d.at)}</span>
                  </>
                )} />
            </section>
            <section className="section">
              <h2>Device eliminati</h2>
              <DeviceList items={data.devices_deleted} empty="Nessuno nel periodo."
                render={(d) => (
                  <>
                    <Link to={`/history?device_id=${d.id}`}>{d.name}</Link> <span className="muted">{formatDateTime(d.at)}</span>
                  </>
                )} />
            </section>
          </div>

          {data.runs.failed.length > 0 && (
            <section className="section">
              <h2>Scansioni non riuscite</h2>
              <DeviceList items={data.runs.failed} empty=""
                render={(r) => (
                  <>
                    <Link to={`/discovery-jobs/${r.job_id}`}>{r.job_name}</Link> <span className="muted">{formatDateTime(r.at)}</span>
                  </>
                )} />
            </section>
          )}

          <section className="section">
            <h2>Apparecchi nuovi in rete</h2>
            {data.endpoints_new.total === 0 ? (
              <p className="muted">Nessun MAC nuovo nelle tabelle degli switch.</p>
            ) : (
              <>
                <EndpointTable items={data.endpoints_new.items} />
                {data.endpoints_new.total > data.endpoints_new.items.length && (
                  <p className="hint">Mostrati i {data.endpoints_new.items.length} più recenti su {data.endpoints_new.total}.</p>
                )}
              </>
            )}
          </section>

          <section className="section">
            <h2>Apparecchi spostati</h2>
            {data.endpoints_moved.total === 0 ? (
              <p className="muted">Nessun MAC ha cambiato porta.</p>
            ) : (
              <EndpointTable items={data.endpoints_moved.items} moved />
            )}
          </section>

          <section className="section">
            <h2>Ultime modifiche</h2>
            {recent.data?.items.length ? (
              <>
                <HistoryList entries={recent.data.items} />
                {recent.data.total > recent.data.items.length && (
                  <p className="hint"><Link to="/history">Tutto lo storico ({recent.data.total} modifiche nel periodo)</Link></p>
                )}
              </>
            ) : (
              <p className="muted">Nessuna modifica nel periodo.</p>
            )}
          </section>
        </>
      )}
    </div>
  )
}
