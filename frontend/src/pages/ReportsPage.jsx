import { useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { qs } from '../api'
import { ErrorBox, Loading, Mono } from '../components/Bits'
import { IconButton, PageIcon } from '../components/Icon'
import PortStatsDialog, { formatBps } from '../components/PortStats'
import { useApi } from '../hooks'
import { formatDateTime, formatSince, formatSpeed } from '../options'
import { LOCALE, t, tc, tn } from '../i18n'

const REPORTS = [
  { value: 'port-usage', label: t('Porte più cariche') },
  { value: 'port-errors', label: t('Errori') },
  { value: 'free-ports', label: t('Porte libere') },
  { value: 'poe', label: t('PoE') },
  { value: 'availability', label: t('Disponibilità') },
]
const PORT_RANGES = [
  { value: '1d', label: t('Ultime 24 ore') },
  { value: '7d', label: t('Ultimi 7 giorni') },
  { value: '30d', label: t('Ultimi 30 giorni') },
]
const AVAILABILITY_RANGES = [
  { value: '7d', label: t('Ultimi 7 giorni') },
  { value: '30d', label: t('Ultimi 30 giorni') },
  { value: '1y', label: t('Ultimo anno') },
]
const FREE_DAYS = [7, 30, 90, 180]

const percent = (value, digits = 1) => (value === null || value === undefined ? '—'
  : `${(value * 100).toLocaleString(LOCALE, { maximumFractionDigits: digits })}%`)

/** CSV con il punto e virgola e il BOM, come l'export dei device: si apre bene con Excel */
function downloadCsv(name, columns, rows) {
  const cell = (value) => {
    // decimali con la virgola dell'Excel italiano (il separatore è già il punto e virgola)
    const text = value === null || value === undefined ? '' : Array.isArray(value) ? value.join(', ')
      : typeof value === 'number' ? value.toLocaleString(LOCALE, { useGrouping: false, maximumFractionDigits: 6 }) : String(value)
    return /[;"\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text
  }
  const lines = [columns.map((c) => cell(c.label)), ...rows.map((row) => columns.map((c) => cell(c.csv ? c.csv(row) : row[c.key])))]
  const blob = new Blob([`﻿${lines.map((l) => l.join(';')).join('\r\n')}\r\n`], { type: 'text/csv;charset=utf-8' })
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = `${name}-${new Date().toISOString().slice(0, 10)}.csv`
  a.click()
  URL.revokeObjectURL(a.href)
}

/** Barra di uso: gialla dal 50%, rossa dall'80% */
function UsageBar({ value }) {
  if (value === null || value === undefined) return <span className="muted">—</span>
  const tone = value >= 0.8 ? 'danger' : value >= 0.5 ? 'warn' : 'ok'
  return (
    <span className={`usage usage--${tone}`}>
      <span className="usage__bar"><span style={{ width: `${Math.min(100, value * 100)}%` }} /></span>
      <span className="usage__value">{percent(value)}</span>
    </span>
  )
}

function DeviceCell({ row }) {
  return (
    <>
      <Link to={`/devices/${row.device_id}`}>{row.device_name}</Link>
      <div className="hint">{[row.site, row.location, row.rack].filter(Boolean).join(' · ')}</div>
    </>
  )
}

function PortCell({ row, onOpen }) {
  return (
    <>
      <button type="button" className="link-button mono" onClick={() => onOpen(row)}
        title={t('Storico di {port}: traffico, errori, PoE', { port: row.interface_name })}>
        {row.interface_name}
      </button>
      {row.description && <div className="hint">{row.description}</div>}
    </>
  )
}

const deviceColumns = [
  { key: 'site', label: t('Sede') },
  { key: 'location', label: t('Posizione') },
  { key: 'rack', label: t('Rack') },
  { key: 'device_name', label: t('Device') },
]

function UsageReport({ data, onOpen }) {
  const columns = [
    ...deviceColumns,
    { key: 'interface_name', label: t('Porta') },
    { key: 'description', label: t('Descrizione') },
    { key: 'remote', label: t('Collegata a'), csv: (r) => (r.remote_device ? `${r.remote_device} ${r.remote_interface || ''}`.trim() : '') },
    { key: 'speed_mbps', label: t('Velocità (Mbit/s)') },
    { key: 'usage', label: t('Uso al 95° percentile (%)'), csv: (r) => (r.usage === null ? '' : Number((r.usage * 100).toFixed(1))) },
    { key: 'in_p95_bps', label: t('Entrata 95° percentile (bit/s)') },
    { key: 'out_p95_bps', label: t('Uscita 95° percentile (bit/s)') },
    { key: 'in_avg_bps', label: t('Entrata media (bit/s)') },
    { key: 'out_avg_bps', label: t('Uscita media (bit/s)') },
    { key: 'in_peak_bps', label: t('Entrata picco (bit/s)') },
    { key: 'out_peak_bps', label: t('Uscita picco (bit/s)') },
    { key: 'in_octets', label: t('Byte ricevuti') },
    { key: 'out_octets', label: t('Byte inviati') },
  ]
  return {
    columns,
    summary: [
      { value: data.saturated, label: t('sature (≥ {p})', { p: percent(data.saturated_at, 0) }), tone: data.saturated ? 'critical' : '' },
      { value: data.total, label: t('porte con traffico') },
    ],
    empty: t('Nessuna porta con traffico nel periodo. Il traffico lo legge il monitor ogni 5 minuti sui device con un profilo SNMP.'),
    table: (
      <table className="table table--dense report">
        <thead>
          <tr>
            <th>{t('Device')}</th>
            <th>{t('Porta')}</th>
            <th>{t('Collegata a')}</th>
            <th>{t('Velocità')}</th>
            <th title={t('Il 95° percentile ignora i picchi del 5% del tempo: è il carico che la porta regge davvero')}>{t('Uso (95° perc.)')}</th>
            <th className="num">{t('Entrata 95°')}</th>
            <th className="num">{t('Uscita 95°')}</th>
            <th className="num">{t('Media')}</th>
            <th className="num">{t('Picco')}</th>
          </tr>
        </thead>
        <tbody>
          {data.items.map((r) => (
            <tr key={r.interface_id} className={r.saturated ? 'report__row--bad' : ''}>
              <td><DeviceCell row={r} /></td>
              <td><PortCell row={r} onOpen={onOpen} /></td>
              <td className="nowrap">{r.remote_device ? <>{r.remote_device} <Mono>{r.remote_interface}</Mono></> : <span className="muted">—</span>}</td>
              <td className="nowrap">{formatSpeed(r.speed_mbps)}</td>
              <td><UsageBar value={r.usage} /></td>
              <td className="num nowrap">{formatBps(r.in_p95_bps)}</td>
              <td className="num nowrap">{formatBps(r.out_p95_bps)}</td>
              <td className="num nowrap">↓{formatBps(r.in_avg_bps)}<div className="hint">↑{formatBps(r.out_avg_bps)}</div></td>
              <td className="num nowrap">↓{formatBps(r.in_peak_bps)}<div className="hint">↑{formatBps(r.out_peak_bps)}</div></td>
            </tr>
          ))}
        </tbody>
      </table>
    ),
  }
}

function ErrorsReport({ data, onOpen }) {
  const columns = [
    ...deviceColumns,
    { key: 'interface_name', label: t('Porta') },
    { key: 'description', label: t('Descrizione') },
    { key: 'speed_mbps', label: t('Velocità (Mbit/s)') },
    { key: 'duplex', label: t('Duplex') },
    { key: 'errors', label: t('Errori') },
    { key: 'discards', label: t('Scarti') },
    { key: 'last_at', label: t('Ultimi errori'), csv: (r) => formatDateTime(r.last_at, { exact: true }) },
  ]
  return {
    columns,
    summary: [{ value: data.total, label: tn(data.total, 'porta con errori o scarti', 'porte con errori o scarti'), tone: data.total ? 'medium' : '' }],
    empty: t('Nessuna porta con errori o pacchetti scartati nel periodo.'),
    table: (
      <table className="table table--dense report">
        <thead>
          <tr>
            <th>{t('Device')}</th>
            <th>{t('Porta')}</th>
            <th>{t('Velocità')}</th>
            <th className="num">{t('Errori')}</th>
            <th className="num">{t('Scarti')}</th>
            <th>{t('Ultimi errori')}</th>
          </tr>
        </thead>
        <tbody>
          {data.items.map((r) => (
            <tr key={r.interface_id}>
              <td><DeviceCell row={r} /></td>
              <td><PortCell row={r} onOpen={onOpen} /></td>
              <td className="nowrap">{formatSpeed(r.speed_mbps)}{r.duplex === 'half' && <span className="badge badge--warn port-flag">{t('half duplex')}</span>}</td>
              <td className="num">{r.errors.toLocaleString(LOCALE)}</td>
              <td className="num">{r.discards.toLocaleString(LOCALE)}</td>
              <td className="nowrap" title={formatDateTime(r.last_at, { exact: true })}>{formatDateTime(r.last_at)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    ),
  }
}

function FreeReport({ data }) {
  const columns = [
    ...deviceColumns,
    { key: 'ports', label: t('Porte') },
    { key: 'up', label: t('Su') },
    { key: 'down', label: t('Giù') },
    { key: 'free', label: t('Libere') },
    { key: 'free_ports', label: t('Porte libere') },
  ]
  // Totali per sede, in testa a ogni gruppo
  const sites = []
  for (const row of data.items) {
    let site = sites.find((s) => s.site_id === row.site_id)
    if (!site) sites.push(site = { site_id: row.site_id, site: row.site, ports: 0, free: 0, rows: [] })
    site.ports += row.ports
    site.free += row.free
    site.rows.push(row)
  }
  return {
    columns,
    summary: [
      { value: data.free, label: t('porte libere da almeno {n} giorni', { n: data.days }), tone: '' },
      { value: data.ports, label: t('porte negli switch letti') },
    ],
    empty: t('Nessuno switch con le porte lette dal monitor. Serve un profilo SNMP sul device.'),
    table: (
      <table className="table table--dense report">
        <thead>
          <tr>
            <th>{t('Device')}</th>
            <th className="num">{t('Porte')}</th>
            <th className="num">{t('Su')}</th>
            <th className="num">{t('Giù')}</th>
            <th className="num">{t('Libere')}</th>
            <th>{t('Quali')}</th>
          </tr>
        </thead>
        {sites.map((site) => (
          <tbody key={site.site_id}>
            <tr className="report__group">
              <th colSpan={6}>{site.site} <span className="muted">{t('{free} libere su {ports}', { free: site.free, ports: site.ports })}</span></th>
            </tr>
            {site.rows.map((r) => (
              <tr key={r.device_id}>
                <td><DeviceCell row={r} /></td>
                <td className="num">{r.ports}</td>
                <td className="num">{r.up}</td>
                <td className="num">{r.down}</td>
                <td className="num"><strong>{r.free}</strong></td>
                <td className="report__names">{r.free_ports.length ? r.free_ports.join(', ') : <span className="muted">—</span>}</td>
              </tr>
            ))}
          </tbody>
        ))}
      </table>
    ),
  }
}

function PoeReport({ data }) {
  const columns = [
    ...deviceColumns,
    { key: 'budget_w', label: t('Disponibili (W)') },
    { key: 'used_w', label: t('Usati (W)') },
    { key: 'usage', label: t('Uso (%)'), csv: (r) => (r.usage === null ? '' : Number((r.usage * 100).toFixed(1))) },
    { key: 'delivering', label: t('Porte che alimentano') },
    { key: 'searching', label: t('Porte in attesa') },
    { key: 'fault', label: t('Porte in guasto') },
  ]
  return {
    columns,
    summary: [
      { value: `${data.used_w} / ${data.budget_w} W`, label: t('usati sul totale disponibile') },
      { value: data.total, label: data.total === 1 ? t('switch PoE') : tc('plurale', 'switch PoE') },
    ],
    empty: t('Nessuno switch PoE letto dal monitor.'),
    table: (
      <table className="table table--dense report">
        <thead>
          <tr>
            <th>{t('Device')}</th>
            <th>{t('Uso')}</th>
            <th className="num">{t('Usati / disponibili')}</th>
            <th className="num">{t('Alimentano')}</th>
            <th className="num">{t('In attesa')}</th>
            <th className="num">{t('Guasto')}</th>
          </tr>
        </thead>
        <tbody>
          {data.items.map((r) => (
            <tr key={r.device_id}>
              <td><DeviceCell row={r} /></td>
              <td><UsageBar value={r.usage} /></td>
              <td className="num nowrap">{r.used_w ?? '—'} / {r.budget_w} W</td>
              <td className="num">{r.delivering}</td>
              <td className="num">{r.searching}</td>
              <td className="num">{r.fault ? <span className="badge badge--danger">{r.fault}</span> : 0}</td>
            </tr>
          ))}
        </tbody>
      </table>
    ),
  }
}

function AvailabilityReport({ data }) {
  const columns = [
    ...deviceColumns,
    { key: 'availability', label: t('Disponibilità (%)'), csv: (r) => (r.availability === null ? '' : Number((r.availability * 100).toFixed(3))) },
    { key: 'checks', label: t('Controlli') },
    { key: 'failed', label: t('Controlli falliti') },
    { key: 'rtt_ms', label: t('Risposta media (ms)') },
    { key: 'reachable', label: t('Adesso'), csv: (r) => (r.reachable === null ? '' : r.reachable ? t('raggiungibile') : t('irraggiungibile')) },
  ]
  const tone = (a) => (a === null ? '' : a >= 0.999 ? 'ok' : a >= 0.99 ? 'warn' : 'danger')
  const below = data.items.filter((r) => r.availability !== null && r.availability < 0.999).length
  return {
    columns,
    summary: [
      { value: below, label: t('sotto il 99,9%'), tone: below ? 'high' : '' },
      { value: data.total, label: t('device controllati dal monitor') },
    ],
    empty: t('Nessun device controllato dal monitor.'),
    table: (
      <table className="table table--dense report">
        <thead>
          <tr>
            <th>{t('Device')}</th>
            <th className="num">{t('Disponibilità')}</th>
            <th className="num">{t('Controlli falliti')}</th>
            <th className="num">{t('Risposta media')}</th>
            <th>{t('Adesso')}</th>
          </tr>
        </thead>
        <tbody>
          {data.items.map((r) => (
            <tr key={r.device_id}>
              <td><DeviceCell row={r} /></td>
              <td className="num">
                {r.availability === null ? <span className="muted">{t('nessun dato')}</span>
                  : <strong className={`tone-text--${tone(r.availability)}`}>{percent(r.availability, 3)}</strong>}
                {r.since && <div className="hint">{t('dati dal {date}', { date: formatDateTime(r.since, { exact: true }) })}</div>}
              </td>
              <td className="num">{r.checks ? `${r.failed} / ${r.checks}` : '—'}</td>
              <td className="num nowrap">{r.rtt_ms === null ? '—' : `${r.rtt_ms.toLocaleString(LOCALE)} ms`}</td>
              <td className="nowrap">
                {r.reachable === null ? <span className="muted">—</span> : (
                  <>
                    <span className={`oper-dot oper-dot--${r.reachable ? 'up' : 'down'}`} />
                    {r.reachable ? t('raggiungibile') : t('irraggiungibile')}
                    {r.reachable_changed_at && <span className="muted"> {formatSince(r.reachable_changed_at)}</span>}
                  </>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    ),
  }
}

const BUILDERS = { 'port-usage': UsageReport, 'port-errors': ErrorsReport, 'free-ports': FreeReport, poe: PoeReport, availability: AvailabilityReport }

/** Dati di un report: montato con key = report */
function Fetch({ url, children }) {
  return children(useApi(url))
}

export default function ReportsPage() {
  const [params, setParams] = useSearchParams()
  const report = REPORTS.some((r) => r.value === params.get('report')) ? params.get('report') : 'port-usage'
  const portRange = params.get('range') || '7d'
  const availabilityRange = params.get('range') || '30d'
  const siteId = params.get('site_id') || ''
  const cabled = params.get('cabled') === '1'
  const days = params.get('days') || '30'
  const [port, setPort] = useState(null)
  const sites = useApi('/sites?limit=500').data

  const query = {
    'port-usage': { range: portRange, site_id: siteId, cabled: cabled ? 'true' : '' },
    'port-errors': { range: portRange, site_id: siteId },
    'free-ports': { days, site_id: siteId },
    poe: { site_id: siteId },
    availability: { range: availabilityRange, site_id: siteId },
  }[report]
  const url = `/reports/${report}${qs(query)}`

  const set = (changes) => setParams((prev) => {
    const next = new URLSearchParams(prev)
    for (const [name, value] of Object.entries(changes)) {
      if (value) next.set(name, value)
      else next.delete(name)
    }
    return next
  }, { replace: true })

  const ranges = report === 'availability' ? AVAILABILITY_RANGES : PORT_RANGES
  const range = report === 'availability' ? availabilityRange : portRange

  return (
    <div className="page">
      <header className="page-head">
        <div>
          <h1 className="page-title"><PageIcon name="chart" />{t('Report')}</h1>
          <p className="page-intro">
            {t('Riepiloghi dallo storico del monitor: porte più cariche, errori, porte libere, PoE e disponibilità dei device. Ognuno si scarica in CSV.')}
          </p>
        </div>
      </header>

      <div className="segmented report-tabs" role="tablist" aria-label={t('Report')}>
        {REPORTS.map((r) => (
          <button key={r.value} type="button" role="tab" aria-selected={report === r.value}
            className={`segmented__item${report === r.value ? ' segmented__item--on' : ''}`}
            onClick={() => set({ report: r.value, range: '' })}>
            {r.label}
          </button>
        ))}
      </div>

      {/* key: cambiando report si riparte da zero, senza disegnare i dati del report di prima con le colonne del nuovo */}
      <Fetch key={report} url={url}>
        {({ data, error, loading }) => {
          const built = data && data.items ? BUILDERS[report]({ data, onOpen: (r) => setPort(r) }) : null
          return (
            <>
          <div className="toolbar">
            {(report === 'port-usage' || report === 'port-errors' || report === 'availability') && (
              <select className="input" aria-label={t('Periodo')} value={range} onChange={(e) => set({ range: e.target.value })}>
                {ranges.map((r) => <option key={r.value} value={r.value}>{r.label}</option>)}
              </select>
            )}
            {report === 'free-ports' && (
              <select className="input" aria-label={t('Giù da almeno')} value={days} onChange={(e) => set({ days: e.target.value === '30' ? '' : e.target.value })}>
                {FREE_DAYS.map((d) => <option key={d} value={d}>{t('Giù da almeno {n} giorni', { n: d })}</option>)}
              </select>
            )}
            {sites && sites.total > 1 && (
              <select className="input" aria-label={t('Sede')} value={siteId} onChange={(e) => set({ site_id: e.target.value })}>
                <option value="">{t('Tutte le sedi')}</option>
                {sites.items.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
              </select>
            )}
            {report === 'port-usage' && (
              <label className="check">
                <input type="checkbox" checked={cabled} onChange={(e) => set({ cabled: e.target.checked ? '1' : '' })} />
                {t('Solo porte con un cavo verso un altro device (uplink)')}
              </label>
            )}
            {built && data.items.length > 0 && (
              <IconButton icon="download" label={t('Scarica in CSV (si apre con Excel)')}
                onClick={() => downloadCsv(`netmap-${report}`, built.columns, data.items)} />
            )}
          </div>

          <ErrorBox error={error} />
          {!data && loading && <Loading />}
          {built && (
            <>
              <div className="problem-counts report-summary">
                {built.summary.map((s) => (
                  <div key={s.label} className={`problem-count problem-count--static${s.tone ? ` problem-count--${s.tone}` : ''}`}>
                    <strong>{s.value}</strong>
                    <span>{s.label}</span>
                  </div>
                ))}
              </div>
              {data.items.length === 0 ? (
                <div className="empty"><p>{built.empty}</p></div>
              ) : (
                <div className="table-wrap">{built.table}</div>
              )}
            </>
          )}
            </>
          )
        }}
      </Fetch>
      {port && (
        <PortStatsDialog port={{ id: port.interface_id, name: port.interface_name, description: port.description }}
          device={port.device_name} onClose={() => setPort(null)} />
      )}
    </div>
  )
}
