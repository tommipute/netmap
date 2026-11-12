import { useEffect } from 'react'
import { Link } from 'react-router-dom'
import { qs } from '../api'
import { useAuth } from '../auth'
import { ErrorBox, Loading, Mono } from '../components/Bits'
import { Icon } from '../components/Icon'
import { useApi } from '../hooks'
import { LOCALE, t, tc, tn } from '../i18n'
import { CountUp } from '../motion'
import { formatDateTime, formatSince } from '../options'
import { RunStatus } from './DiscoveryJobPage'

/**
 * Panoramica: la pagina iniziale. Tutto da GET /api/dashboard (services/dashboard.py), riletto ogni minuto: i
 * numeri scivolano al valore nuovo, le animazioni d'entrata partono solo la prima volta (chiavi stabili).
 */

const RELOAD_MS = 60_000

function greeting() {
  const hour = new Date().getHours()
  if (hour < 5 || hour >= 18) return t('Buonasera')
  return hour < 13 ? t('Buongiorno') : t('Buon pomeriggio')
}

/** Il riassunto in parole sotto il saluto. */
function summaryText(data) {
  const { counts, live, pending_changes: pending, system } = data
  const parts = [
    t('NetMap documenta {devices} in {sites}, con {cables} e {prefixes}.', {
      devices: tn(counts.devices, '1 device', '{n} device'),
      sites: tn(counts.sites, '1 sede', '{n} sedi'),
      cables: tn(counts.cables, '1 cavo', '{n} cavi'),
      prefixes: tn(counts.prefixes, '1 subnet', '{n} subnet'),
    }),
  ]
  const checked = live.up + live.down
  if (live.down) parts.push(tn(live.down, '1 device non risponde.', '{n} device non rispondono.'))
  else if (checked) parts.push(t('Tutti i device controllati rispondono.'))
  if (pending) parts.push(tn(pending, '1 modifica della scansione aspetta la tua approvazione.', '{n} modifiche della scansione aspettano la tua approvazione.'))
  if (system?.update_available) parts.push(t('È disponibile una versione nuova di NetMap.'))
  return parts.join(' ')
}

function Kpi({ icon, tone, label, value, detail, to }) {
  return (
    <Link to={to} className={`kpi kpi--${tone}`}>
      <span className="kpi__icon"><Icon name={icon} size={20} /></span>
      <span className="kpi__label">{label}</span>
      <span className="kpi__value"><CountUp value={value} /></span>
      {detail && <span className="kpi__detail">{detail}</span>}
    </Link>
  )
}

function Card({ title, icon, link, linkLabel, wide = false, children }) {
  return (
    <section className={`card${wide ? ' card--wide' : ''}`}>
      <header className="card__head">
        <h2>{icon && <Icon name={icon} />}{title}</h2>
        {link && (
          <Link to={link} className="card__link">
            {linkLabel || t('Apri')} <Icon name="arrowRight" size={14} />
          </Link>
        )}
      </header>
      {children}
    </section>
  )
}

/** Anello dello stato live: rispondono, non rispondono, mai controllati. */
function Donut({ live }) {
  const total = live.up + live.down + live.unknown
  const r = 52
  const length = 2 * Math.PI * r
  let offset = 0
  const parts = [
    { key: 'up', value: live.up, className: 'donut__seg--up' },
    { key: 'down', value: live.down, className: 'donut__seg--down' },
    { key: 'unknown', value: live.unknown, className: 'donut__seg--unknown' },
  ].filter((p) => p.value > 0)
  const percent = total ? Math.round((live.up / total) * 100) : 0
  return (
    <div className="donut">
      <svg viewBox="0 0 128 128" width="128" height="128" aria-hidden="true">
        <circle cx="64" cy="64" r={r} className="donut__track" />
        <g className="donut__ring">
          {parts.map((p) => {
            const size = (p.value / total) * length
            const seg = (
              <circle key={p.key} cx="64" cy="64" r={r} className={`donut__seg ${p.className}`}
                strokeDasharray={`${Math.max(size - (parts.length > 1 ? 3 : 0), 0.01)} ${length}`}
                strokeDashoffset={-offset} />
            )
            offset += size
            return seg
          })}
        </g>
      </svg>
      <div className="donut__center">
        <strong><CountUp value={percent} />%</strong>
        <span>{t('rispondono')}</span>
      </div>
    </div>
  )
}

function LiveCard({ live }) {
  const total = live.up + live.down + live.unknown
  return (
    <Card title={t('Stato live')} icon="activity" link="/devices?reachable=false" linkLabel={t('Chi non risponde')}>
      {total === 0 ? (
        <p className="muted">{t('Nessun device da controllare: serve un IP di management e lo stato attivo o offline.')}</p>
      ) : (
        <>
          <div className="live-card">
            <Donut live={live} />
            <ul className="legend">
              <li><span className="legend__dot legend__dot--up" />{t('Rispondono')} <strong>{live.up}</strong></li>
              <li><span className="legend__dot legend__dot--down" />{t('Non rispondono')} <strong>{live.down}</strong></li>
              {live.unknown > 0 && <li><span className="legend__dot legend__dot--unknown" />{t('Mai controllati')} <strong>{live.unknown}</strong></li>}
            </ul>
          </div>
          {live.down_devices.length > 0 && (
            <ul className="dash-list">
              {live.down_devices.map((d) => (
                <li key={d.id}>
                  <span className="live-dot live-dot--down" />
                  <Link to={`/devices/${d.id}`}>{d.name}</Link>
                  <span className="muted">{formatSince(d.at)}</span>
                </li>
              ))}
            </ul>
          )}
          {live.last_check_at && <p className="hint">{t('Ultimo controllo: {when}', { when: formatDateTime(live.last_check_at) })}</p>}
        </>
      )}
    </Card>
  )
}

/** Modifiche al giorno: barre che crescono a onda. */
function ActivityCard({ days }) {
  const total = days.reduce((sum, d) => sum + d.count, 0)
  const max = Math.max(1, ...days.map((d) => d.count))
  const label = (day) => new Date(`${day}T12:00:00`).toLocaleDateString(LOCALE, { weekday: 'short', day: 'numeric' })
  return (
    <Card title={t('Attività')} icon="history" link="/history" linkLabel={t('Storico')} wide>
      <p className="card__lead">
        {tn(total, '1 modifica negli ultimi 14 giorni', '{n} modifiche negli ultimi 14 giorni')}
      </p>
      <div className="bars" role="img" aria-label={t('Modifiche al giorno negli ultimi 14 giorni')}>
        {days.map((d, i) => (
          <div key={d.day} className="bars__col" title={`${label(d.day)}: ${tn(d.count, '1 modifica', '{n} modifiche')}`}>
            <span className="bars__value">{d.count || ''}</span>
            <span className={`bars__bar${d.count ? '' : ' bars__bar--zero'}`}
              style={{ height: `${Math.max((d.count / max) * 100, 3)}%`, '--i': i }} />
            <span className="bars__day">
              <span className="bars__weekday">{new Date(`${d.day}T12:00:00`).toLocaleDateString(LOCALE, { weekday: 'short' })} </span>
              {Number(d.day.slice(8))}
            </span>
          </div>
        ))}
      </div>
    </Card>
  )
}

/** Barre orizzontali: ruoli e sedi. */
function HBars({ rows }) {
  const max = Math.max(1, ...rows.map((r) => r.count))
  return (
    <ul className="hbars">
      {rows.map((r, i) => (
        <li key={r.key} className={r.muted ? 'hbars--muted' : undefined}>
          <span className="hbars__label">{r.to ? <Link to={r.to}>{r.label}</Link> : r.label}</span>
          <span className="hbars__track">
            <span className="hbars__fill" style={{ width: `${(r.count / max) * 100}%`, '--i': i, ...(r.color ? { background: r.color } : {}) }} />
          </span>
          <span className="hbars__value">{r.count}{r.extra}</span>
        </li>
      ))}
    </ul>
  )
}

function RolesCard({ roles }) {
  const rows = roles.map((r) => ({
    key: r.id ?? (r.none ? 'none' : 'others'),
    label: r.none ? t('Senza ruolo') : r.others ? t('Altri ruoli') : r.name,
    muted: r.none || r.others,
    to: r.id ? `/devices${qs({ role_id: r.id })}` : null,
    color: r.color,
    count: r.count,
  }))
  return (
    <Card title={t('Device per ruolo')} icon="tag" link="/device-roles" linkLabel={t('Ruoli')}>
      {rows.length ? <HBars rows={rows} /> : <p className="muted">{t('Ancora nessun device.')}</p>}
    </Card>
  )
}

function SitesCard({ sites, total }) {
  const rows = sites.map((s) => ({
    key: s.id,
    label: s.name,
    to: `/devices${qs({ site_id: s.id })}`,
    count: s.count,
    extra: s.down ? <span className="hbars__down" title={t('{n} non rispondono', { n: s.down })}> · {s.down} ↓</span> : null,
  }))
  return (
    <Card title={t('Device per sede')} icon="building" link="/sites" linkLabel={tn(total, '1 sede', '{n} sedi')}>
      {rows.length ? <HBars rows={rows} /> : <p className="muted">{t('Ancora nessun device.')}</p>}
    </Card>
  )
}

function PrefixesCard({ prefixes }) {
  return (
    <Card title={t('Subnet più piene')} icon="network" link="/prefixes" linkLabel={tn(prefixes.total, '1 subnet', '{n} subnet')}>
      {prefixes.items.length === 0 ? (
        <p className="muted">{t('Nessuna subnet documentata.')}</p>
      ) : (
        <ul className="dash-meters">
          {prefixes.items.map((p, i) => (
            <li key={p.id}>
              <div className="dash-meters__head">
                <Link to={`/prefixes/${p.id}`}><Mono>{p.prefix}</Mono></Link>
                <span className="muted">{p.description}</span>
                <span className="dash-meters__percent">{p.percent.toLocaleString(LOCALE)}%</span>
              </div>
              <div className={`meter${p.percent >= 90 ? ' meter--danger' : p.percent >= 75 ? ' meter--warn' : ''}`}>
                <div className="meter__fill" style={{ width: `${Math.max(p.percent, 1)}%`, '--i': i }} />
              </div>
              <span className="hint">{t('{used} IP usati su {total}', { used: p.used, total: p.total })}</span>
            </li>
          ))}
        </ul>
      )}
      {prefixes.partial && <p className="hint">{t('Cercate tra le 300 subnet più piccole.')}</p>}
    </Card>
  )
}

function NetworkCard({ counts, ports, endpoints }) {
  const facts = [
    { to: '/cables', icon: 'cable', label: t('Cavi'), value: counts.cables },
    { to: '/racks', icon: 'stack', label: t('Rack'), value: counts.racks },
    { to: '/ip-addresses', icon: 'hash', label: t('Indirizzi IP'), value: counts.ip_addresses },
    { to: '/vlans', icon: 'layers', label: t('VLAN'), value: counts.vlans },
    { to: '/where', icon: 'locate', label: t('Endpoint'), value: endpoints.total },
    { to: '/maps', icon: 'map', label: t('Mappe'), value: counts.maps },
  ]
  const cabled = ports.total ? Math.round((ports.cabled / ports.total) * 100) : 0
  return (
    <Card title={t('La rete in numeri')} icon="share">
      <div className="minis">
        {facts.map((f) => (
          <Link key={f.to} to={f.to} className="mini">
            <Icon name={f.icon} />
            <strong><CountUp value={f.value} /></strong>
            <span>{f.label}</span>
          </Link>
        ))}
      </div>
      <div className="dash-meters__head">
        <span>{t('Porte collegate con un cavo')}</span>
        <span className="dash-meters__percent">{ports.cabled} / {ports.total}</span>
      </div>
      <div className="meter"><div className="meter__fill" style={{ width: `${Math.max(cabled, 1)}%` }} /></div>
      <p className="hint">
        {t('Stato delle porte dall\'ultimo controllo: {up} attive, {down} giù.', { up: ports.up, down: ports.down })}
        {(endpoints.new_day > 0 || endpoints.moved_day > 0) && (
          <> {t('Nelle ultime 24 ore: {new} apparecchi nuovi, {moved} spostati.', { new: endpoints.new_day, moved: endpoints.moved_day })}{' '}
            <Link to="/whats-changed">{t('Cosa è cambiato')}</Link></>
        )}
      </p>
    </Card>
  )
}

function ScansCard({ runs, pending }) {
  return (
    <Card title={t('Scansioni SNMP')} icon="radar" link="/discovery-jobs" linkLabel={tn(runs.jobs, '1 scansione', '{n} scansioni')}>
      {pending > 0 && (
        <Link to="/discovery/changes" className="callout callout--warn">
          <Icon name="inbox" />
          <span>{tn(pending, '1 modifica da approvare', '{n} modifiche da approvare')}</span>
          <Icon name="arrowRight" size={14} />
        </Link>
      )}
      {runs.last.length === 0 ? (
        <p className="muted">{t('Nessuna scansione eseguita.')}</p>
      ) : (
        <ul className="dash-list">
          {runs.last.map((r) => (
            <li key={r.id}>
              <Link to={`/discovery-jobs/${r.job_id}`}>{r.job_name}</Link>
              <RunStatus status={r.status} />
              <span className="muted dash-list__end">{formatDateTime(r.at)}</span>
            </li>
          ))}
        </ul>
      )}
      {runs.failed_week > 0 && (
        <p className="hint hint--danger">{tn(runs.failed_week, '1 scansione non riuscita negli ultimi 7 giorni.', '{n} scansioni non riuscite negli ultimi 7 giorni.')}</p>
      )}
    </Card>
  )
}

function MapsCard({ maps }) {
  return (
    <Card title={t('Mappe')} icon="map" link="/maps" linkLabel={t('Tutte')}>
      {maps.length === 0 ? (
        <p className="muted">{t('Ancora nessuna mappa.')}</p>
      ) : (
        <ul className="map-links">
          {maps.map((m) => (
            <li key={m.id}>
              <Link to={`/maps/${m.id}`}>
                <span className="map-links__icon"><Icon name="map" /></span>
                <span className="map-links__text"><strong>{m.name}</strong><span className="muted">{m.site_name}</span></span>
                <Icon name="arrowRight" size={14} />
              </Link>
            </li>
          ))}
        </ul>
      )}
    </Card>
  )
}

function SystemCard({ system }) {
  const manual = system.kind === 'manual'
  const backup = manual ? null : system.last_backup
  const version = system.available?.version || system.available?.short
  return (
    <Card title={t('Sistema')} icon="settings">
      <ul className="dash-list dash-list--icons">
        <li>
          <Icon name={manual ? 'refresh' : system.update_available ? 'cloudDownload' : 'ok'} />
          <Link to="/updates">
            {manual ? t('Aggiornamenti a mano') : system.update_available
              ? t('Versione nuova disponibile{v}', { v: version ? ` (${version})` : '' })
              : t('NetMap è aggiornato')}
          </Link>
          {system.update_available && <span className="badge badge--info dash-list__end">{t('Nuova')}</span>}
        </li>
        <li>
          <Icon name={backup && !backup.ok ? 'alert' : 'database'} />
          <Link to="/backup">
            {manual ? t('Backup a mano') : !backup ? t('Ancora nessun backup') : backup.ok
              ? t('Ultimo backup {when}', { when: formatDateTime(backup.at) })
              : t('Ultimo backup non riuscito')}
          </Link>
          {backup && !backup.ok && <span className="badge badge--danger dash-list__end">{t('Errore')}</span>}
        </li>
      </ul>
    </Card>
  )
}

export default function DashboardPage() {
  const { user } = useAuth()
  const { data, error, loading, reload } = useApi('/dashboard')
  useEffect(() => {
    const timer = setInterval(() => !document.hidden && reload(), RELOAD_MS)
    return () => clearInterval(timer)
  }, [reload])
  const name = user?.first_name || user?.full_name || user?.username
  const today = new Date().toLocaleDateString(LOCALE, { weekday: 'long', day: 'numeric', month: 'long' })

  return (
    <div className="page dash">
      <header className="dash-hello">
        <div>
          <p className="dash-hello__date">{today}</p>
          <h1>{name ? `${greeting()}, ${name}` : greeting()}</h1>
          {data && <p className="dash-hello__text">{summaryText(data)}</p>}
        </div>
      </header>
      <ErrorBox error={error} />
      {!data && loading && <Loading />}
      {data && (
        <>
          <div className="kpis">
            <Kpi icon="server" tone="accent" label={tc('elenco', 'Device')} value={data.counts.devices} to="/devices"
              detail={t('{sites} · {racks}', { sites: tn(data.counts.sites, '1 sede', '{n} sedi'), racks: tn(data.counts.racks, '1 rack', '{n} rack') })} />
            <Kpi icon="ok" tone="ok" label={t('Rispondono')} value={data.live.up} to="/devices?reachable=true"
              detail={t('su {n} controllati', { n: data.live.up + data.live.down + data.live.unknown })} />
            <Kpi icon="alert" tone={data.live.down ? 'danger' : 'muted'} label={t('Non rispondono')} value={data.live.down}
              to="/devices?reachable=false" detail={data.live.down ? t('al ping e all\'SNMP') : t('nessun problema')} />
            <Kpi icon="inbox" tone={data.pending_changes ? 'warn' : 'muted'} label={t('Da approvare')} value={data.pending_changes}
              to="/discovery/changes" detail={t('proposte dalla scansione')} />
          </div>
          <div className="dash-grid">
            <LiveCard live={data.live} />
            <ActivityCard days={data.activity} />
            <RolesCard roles={data.roles} />
            <SitesCard sites={data.sites} total={data.counts.sites} />
            <PrefixesCard prefixes={data.prefixes} />
            <NetworkCard counts={data.counts} ports={data.ports} endpoints={data.endpoints} />
            <ScansCard runs={data.runs} pending={data.pending_changes} />
            <MapsCard maps={data.maps} />
            {data.system && <SystemCard system={data.system} />}
          </div>
        </>
      )}
    </div>
  )
}
