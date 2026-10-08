import { useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { qs } from '../api'
import { ErrorBox, Loading, Mono } from '../components/Bits'
import HistoryList, { SOURCES } from '../components/HistoryList'
import { useApi } from '../hooks'
import { formatDateTime, formatSince } from '../options'
import { t } from '../i18n'

const PERIODS = [
  { hours: 24, label: t('Ultime 24 ore') },
  { hours: 24 * 7, label: t('Ultimi 7 giorni') },
  { hours: 24 * 30, label: t('Ultimi 30 giorni') },
]

const SHOWN = 5 // nelle liste dei device: gli ultimi 5, gli altri con "Mostra tutti"

/** Riquadro con il numero: porta a un'altra pagina (to) o alla sua sezione in questa pagina (section). */
function Tile({ value, label, detail, to, section, tone }) {
  const body = (
    <>
      <span className="tile__value">{value}</span>
      <span className="tile__label">{label}</span>
      {detail && <span className="tile__detail">{detail}</span>}
    </>
  )
  const className = `tile${tone && value ? ` tile--${tone}` : ''}`
  if (to) return <Link to={to} className={className}>{body}</Link>
  if (section) {
    return (
      <button type="button" className={className}
        onClick={() => document.getElementById(section)?.scrollIntoView({ behavior: 'smooth', block: 'start' })}>
        {body}
      </button>
    )
  }
  return <div className={className}>{body}</div>
}

/** Elenco dei device, dal più recente: i primi 5 e "Mostra tutti" per il resto. */
function DeviceList({ items, empty, render }) {
  const [all, setAll] = useState(false)
  if (items.length === 0) return <p className="muted">{empty}</p>
  const shown = all ? items : items.slice(0, SHOWN)
  return (
    <>
      <ul className="plain-list">
        {shown.map((d) => (
          <li key={`${d.id}-${d.at}`}>{render(d)}</li>
        ))}
      </ul>
      {items.length > SHOWN && (
        <button type="button" className="link-button" onClick={() => setAll((v) => !v)}>
          {all ? t('Mostra solo gli ultimi 5') : t('Mostra tutti ({n})', { n: items.length })}
        </button>
      )}
    </>
  )
}

function EndpointTable({ items, moved }) {
  return (
    <div className="table-wrap">
      <table className="table table--dense">
        <thead>
          <tr>
            <th>{t('MAC')}</th>
            <th>{t('IP')}</th>
            <th>{moved ? t('Adesso su') : t('Switch e porta')}</th>
            {moved && <th>{t('Prima su')}</th>}
            <th>{t('VLAN')}</th>
            <th>{moved ? t('Spostato') : t('Visto la prima volta')}</th>
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
                {e.device_id ? <><Link to={`/devices/${e.device_id}`}>{e.device_name}</Link> <Mono>{e.interface_name}</Mono></> : <span className="muted">{t('porta eliminata')}</span>}
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
  const historyLink = since ? `/history${qs({ since })}` : '/history' // storico dello stesso periodo

  const sourceText = data
    ? SOURCES.filter((s) => data.changes.by_source[s.value]).map((s) => `${s.label.toLowerCase()} ${data.changes.by_source[s.value]}`).join(', ')
    : ''

  return (
    <div className="page">
      <header className="page-head">
        <div>
          <h1>{t('Cosa è cambiato')}</h1>
          <p className="page-intro">
            {t('Il riassunto del periodo: modifiche alla documentazione, device che non rispondono, apparecchi nuovi o spostati visti dalla scansione.')}
          </p>
        </div>
      </header>

      <div className="toolbar">
        <div className="segmented" role="group" aria-label={t('Periodo')}>
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
            <Tile value={data.devices_down.length} label={t('Non rispondono')} tone="danger"
              detail={data.devices_down.some((d) => d.new) ? `${data.devices_down.filter((d) => d.new).length} nel periodo` : null}
              to="/devices?reachable=false" />
            <Tile value={data.devices_back.length} label={t('Tornati a rispondere')} tone="ok" section="tornati" />
            <Tile value={data.changes.total} label={t('Modifiche')} detail={sourceText || null} to={historyLink} />
            <Tile value={data.endpoints_new.total} label={t('Apparecchi nuovi in rete')} tone="info" section="nuovi" />
            <Tile value={data.endpoints_moved.total} label={t('Apparecchi spostati')} tone="warn" section="spostati" />
            <Tile value={data.runs.total} label={t('Scansioni')}
              detail={data.runs.failed.length ? t('{n} non riuscite', { n: data.runs.failed.length }) : null} tone={data.runs.failed.length ? 'danger' : null} to="/discovery-jobs" />
            <Tile value={data.pending_changes} label={t('Da approvare')} tone="warn" to="/discovery/changes" />
          </div>

          <div className="two-cols">
            <section className="section">
              <h2>{t('Non rispondono')}</h2>
              <DeviceList items={data.devices_down} empty={t('Tutti i device controllati rispondono.')}
                render={(d) => (
                  <>
                    <span className="live-dot live-dot--down" /> <Link to={`/devices/${d.id}`}>{d.name}</Link>{' '}
                    <span className="muted">{formatSince(d.at)}</span> {d.new && <span className="tag">{t('nuovo')}</span>}
                  </>
                )} />
            </section>
            <section className="section" id="tornati">
              <h2>{t('Tornati a rispondere')}</h2>
              <DeviceList items={data.devices_back} empty={t('Nessuno nel periodo.')}
                render={(d) => (
                  <>
                    <span className="live-dot live-dot--up" /> <Link to={`/devices/${d.id}`}>{d.name}</Link>{' '}
                    <span className="muted">{formatDateTime(d.at)}</span>
                  </>
                )} />
            </section>
            <section className="section">
              <h2>{t('Device aggiunti')}</h2>
              <DeviceList items={data.devices_created} empty={t('Nessuno nel periodo.')}
                render={(d) => (
                  <>
                    {d.exists ? <Link to={`/devices/${d.id}`}>{d.name}</Link> : <span className="muted">{d.name} (poi eliminato)</span>}{' '}
                    <span className="muted">{formatDateTime(d.at)}</span>
                  </>
                )} />
            </section>
            <section className="section">
              <h2>{t('Device eliminati')}</h2>
              <DeviceList items={data.devices_deleted} empty={t('Nessuno nel periodo.')}
                render={(d) => (
                  <>
                    <Link to={`/history?device_id=${d.id}`}>{d.name}</Link> <span className="muted">{formatDateTime(d.at)}</span>
                  </>
                )} />
            </section>
          </div>

          {data.runs.failed.length > 0 && (
            <section className="section">
              <h2>{t('Scansioni non riuscite')}</h2>
              <DeviceList items={data.runs.failed} empty=""
                render={(r) => (
                  <>
                    <Link to={`/discovery-jobs/${r.job_id}`}>{r.job_name}</Link> <span className="muted">{formatDateTime(r.at)}</span>
                  </>
                )} />
            </section>
          )}

          <section className="section" id="nuovi">
            <h2>{t('Apparecchi nuovi in rete')}</h2>
            {data.endpoints_new.total === 0 ? (
              <p className="muted">{t('Nessun MAC nuovo nelle tabelle degli switch.')}</p>
            ) : (
              <>
                <EndpointTable items={data.endpoints_new.items} />
                {data.endpoints_new.total > data.endpoints_new.items.length && (
                  <p className="hint">{t('Mostrati i {n} più recenti su {total}.', { n: data.endpoints_new.items.length, total: data.endpoints_new.total })}</p>
                )}
              </>
            )}
          </section>

          <section className="section" id="spostati">
            <h2>{t('Apparecchi spostati')}</h2>
            {data.endpoints_moved.total === 0 ? (
              <p className="muted">{t('Nessun MAC ha cambiato porta.')}</p>
            ) : (
              <EndpointTable items={data.endpoints_moved.items} moved />
            )}
          </section>

          <section className="section">
            <h2>{t('Ultime modifiche')}</h2>
            {recent.data?.items.length ? (
              <>
                <HistoryList entries={recent.data.items} />
                {recent.data.total > recent.data.items.length && (
                  <p className="hint"><Link to={historyLink}>Tutto lo storico ({recent.data.total} modifiche nel periodo)</Link></p>
                )}
              </>
            ) : (
              <p className="muted">{t('Nessuna modifica nel periodo.')}</p>
            )}
          </section>
        </>
      )}
    </div>
  )
}
