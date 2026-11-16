// Storico di una porta: traffico, errori, tempo su e PoE, dai punti salvati dal monitor (services/port_stats.py)
import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { useApi } from '../hooks'
import { LOCALE, t } from '../i18n'
import { formatSpeed } from '../options'
import { ErrorBox, Loading, Mono } from './Bits'
import Modal from './Modal'

const RANGES = [
  { value: '1d', label: t('1 giorno') },
  { value: '2d', label: t('2 giorni') },
  { value: '7d', label: t('7 giorni') },
  { value: '30d', label: t('30 giorni') },
  { value: '1y', label: t('1 anno') },
]
const HEIGHT = { traffic: 190, small: 90 }
const PAD = { top: 10, right: 12, bottom: 22, left: 64 }
const HOUR = 3600000
const DAY = 24 * HOUR

function number(value, digits = 1) {
  return value.toLocaleString(LOCALE, { maximumFractionDigits: digits })
}

/** 12345678 -> "12,3 Mbit/s" */
export function formatBps(bps) {
  if (bps === null || bps === undefined) return '—'
  const units = [[1e9, 'Gbit/s'], [1e6, 'Mbit/s'], [1e3, 'kbit/s']]
  const [size, unit] = units.find(([s]) => bps >= s) || [1, 'bit/s']
  return `${number(bps / size, bps / size >= 100 ? 0 : 1)} ${unit}`
}

function formatBytes(bytes) {
  if (bytes === null || bytes === undefined) return '—'
  const units = [[1e12, 'TB'], [1e9, 'GB'], [1e6, 'MB'], [1e3, 'kB']]
  const [size, unit] = units.find(([s]) => bytes >= s) || [1, 'B']
  return `${number(bytes / size)} ${unit}`
}

function percent(fraction, digits = 1) {
  return `${number(fraction * 100, digits)}%`
}

/** Fondo scala "tondo" (1, 2, 5 × 10^n) con 4 tacche */
function niceScale(max) {
  if (!max) return { top: 1, ticks: [0, 1] }
  const raw = max / 4
  const power = 10 ** Math.floor(Math.log10(raw))
  const step = [1, 2, 2.5, 5, 10].map((m) => m * power).find((s) => s >= raw)
  const top = Math.ceil(max / step) * step
  const ticks = []
  for (let v = 0; v <= top + step / 2; v += step) ticks.push(v)
  return { top, ticks }
}

/** Tacche del tempo (ora locale): ogni tot ore, giorni o mesi, abbastanza distanti da leggersi */
function timeTicks(start, end, width) {
  const span = end - start
  const steps = [HOUR, 2 * HOUR, 3 * HOUR, 6 * HOUR, 12 * HOUR, DAY, 2 * DAY, 3 * DAY, 7 * DAY, 30 * DAY]
  const step = steps.find((s) => span / s <= width / 70) || 30 * DAY
  const ticks = []
  const first = new Date(start)
  if (step >= 30 * DAY) {
    first.setHours(0, 0, 0, 0)
    first.setDate(1)
    for (let d = new Date(first); d <= end; d.setMonth(d.getMonth() + 1)) if (d >= start) ticks.push(new Date(d))
    return { ticks, label: (d) => d.toLocaleDateString(LOCALE, { month: 'short' }) }
  }
  if (step >= DAY) {
    first.setHours(0, 0, 0, 0)
    const days = step / DAY
    for (let d = new Date(first); d <= end; d.setDate(d.getDate() + 1)) {
      if (d >= start && (step === 7 * DAY ? d.getDay() === 1 : Math.round((d - first) / DAY) % days === 0)) ticks.push(new Date(d))
    }
    return { ticks, label: (d) => d.toLocaleDateString(LOCALE, { day: 'numeric', month: 'numeric' }) }
  }
  first.setMinutes(0, 0, 0)
  const hours = step / HOUR
  for (let d = new Date(first); d <= end; d.setHours(d.getHours() + 1)) {
    if (d >= start && d.getHours() % hours === 0) ticks.push(new Date(d))
  }
  return {
    ticks,
    label: (d) => (d.getHours() === 0
      ? d.toLocaleDateString(LOCALE, { day: 'numeric', month: 'numeric' })
      : d.toLocaleTimeString(LOCALE, { hour: '2-digit', minute: '2-digit' })),
  }
}

function useWidth() {
  const ref = useRef(null)
  const [width, setWidth] = useState(600)
  useLayoutEffect(() => {
    if (!ref.current) return undefined
    const observer = new ResizeObserver(([entry]) => setWidth(Math.max(260, Math.round(entry.contentRect.width))))
    observer.observe(ref.current)
    return () => observer.disconnect()
  }, [])
  return [ref, width]
}

/** Spezzata dei punti; si interrompe dove mancano punti (monitor fermo, porta non letta) */
function linePath(points, key, x, y, step) {
  let d = ''
  let last = null
  for (const p of points) {
    const value = p[key]
    if (value === null || value === undefined) {
      last = null
      continue
    }
    const gap = last !== null && p.time - last > step * 1.5
    d += `${!last || gap ? 'M' : 'L'}${x(p.time + step / 2).toFixed(1)},${y(value).toFixed(1)}`
    last = p.time
  }
  return d
}

function areaPath(points, key, x, y, step, base) {
  const parts = []
  let run = []
  const flush = () => {
    if (run.length) {
      const top = run.map((p, i) => `${i ? 'L' : 'M'}${x(p.time + step / 2).toFixed(1)},${y(p[key]).toFixed(1)}`).join('')
      parts.push(`${top}L${x(run[run.length - 1].time + step / 2).toFixed(1)},${base}L${x(run[0].time + step / 2).toFixed(1)},${base}Z`)
    }
    run = []
  }
  for (const p of points) {
    if (p[key] === null || p[key] === undefined || (run.length && p.time - run[run.length - 1].time > step * 1.5)) flush()
    if (p[key] !== null && p[key] !== undefined) run.push(p)
  }
  flush()
  return parts.join('')
}

/**
 * Un grafico nel tempo. `series`: [{ key, label, className, kind: 'area' | 'line' | 'bar' }].
 * `hover` è condiviso tra i grafici della finestra: passando il mouse su uno si vede lo stesso momento su tutti.
 */
function TimeChart({ data, points, series, height, format, max, hover, onHover, title }) {
  const [ref, width] = useWidth()
  const start = new Date(data.start).getTime()
  const end = new Date(data.end).getTime()
  const step = data.step * 1000
  const plotW = width - PAD.left - PAD.right
  const plotH = height - PAD.top - PAD.bottom
  const highest = max ?? Math.max(0, ...points.flatMap((p) => series.map((s) => p[s.key] ?? 0)))
  const scale = niceScale(highest)
  const x = (time) => PAD.left + ((time - start) / (end - start)) * plotW
  const y = (value) => PAD.top + plotH - (value / scale.top) * plotH
  const base = PAD.top + plotH
  const time = timeTicks(new Date(start), new Date(end), plotW)
  const barW = Math.max(1, (step / (end - start)) * plotW - 1)

  const move = (e) => {
    const rect = e.currentTarget.getBoundingClientRect()
    const at = start + ((e.clientX - rect.left - PAD.left) / plotW) * (end - start)
    let best = null
    for (const p of points) if (!best || Math.abs(p.time + step / 2 - at) < Math.abs(best.time + step / 2 - at)) best = p
    onHover(best && Math.abs(best.time + step / 2 - at) <= step * 2 ? best.time : null)
  }
  const current = hover !== null ? points.find((p) => p.time === hover) : null

  return (
    <div className="port-chart" ref={ref}>
      <div className="port-chart__head">
        <h3>{title}</h3>
        <div className="port-chart__legend">
          {series.map((s) => (
            <span key={s.key} className={`port-chart__key ${s.className}`}>{s.label}</span>
          ))}
        </div>
      </div>
      <svg width={width} height={height} className="port-chart__svg" onMouseMove={move} onMouseLeave={() => onHover(null)} role="img" aria-label={title}>
        {scale.ticks.map((v) => (
          <g key={v}>
            <line className="port-chart__grid" x1={PAD.left} x2={width - PAD.right} y1={y(v)} y2={y(v)} />
            <text className="port-chart__axis" x={PAD.left - 6} y={y(v) + 4} textAnchor="end">{format(v, true)}</text>
          </g>
        ))}
        {time.ticks.map((d) => (
          <text key={d.getTime()} className="port-chart__axis" x={x(d.getTime())} y={height - 6} textAnchor="middle">{time.label(d)}</text>
        ))}
        {series.map((s) => {
          if (s.kind === 'bar') {
            return (
              <g key={s.key} className={s.className}>
                {points.filter((p) => p[s.key]).map((p) => (
                  <rect key={p.time} x={x(p.time)} width={barW} y={y(p[s.key])} height={base - y(p[s.key])} />
                ))}
              </g>
            )
          }
          const d = s.kind === 'area' ? areaPath(points, s.key, x, y, step, base) : linePath(points, s.key, x, y, step)
          return <path key={s.key} d={d} className={`${s.className} port-chart__${s.kind}`} />
        })}
        {current && <line className="port-chart__cursor" x1={x(current.time + step / 2)} x2={x(current.time + step / 2)} y1={PAD.top} y2={base} />}
      </svg>
      {current && (
        <div className="port-chart__tip" style={{ left: Math.min(x(current.time + step / 2) + 10, width - 200) }}>
          <div className="muted">{when(current.time, data.period)}</div>
          {series.map((s) => (
            <div key={s.key} className={`port-chart__key ${s.className}`}>{s.label}: <strong>{format(current[s.key] ?? null)}</strong></div>
          ))}
          {series.some((s) => s.peak) && series.filter((s) => s.peak && current[s.peak]).map((s) => (
            <div key={s.peak} className="muted">{t('picco {name}: {value}', { name: s.label.toLowerCase(), value: format(current[s.peak]) })}</div>
          ))}
        </div>
      )}
    </div>
  )
}

/** Il momento di un punto: ore e minuti (5 minuti), ora (ore), giorno (giorni) */
function when(time, period) {
  const d = new Date(time)
  if (period === '1d') return d.toLocaleDateString(LOCALE, { weekday: 'short', day: 'numeric', month: 'short', year: 'numeric' })
  const end = new Date(time + (period === '1h' ? HOUR : 5 * 60000))
  const hm = (date) => date.toLocaleTimeString(LOCALE, { hour: '2-digit', minute: '2-digit' })
  return `${d.toLocaleDateString(LOCALE, { weekday: 'short', day: 'numeric', month: 'short' })} ${hm(d)}–${hm(end)}`
}

/** Striscia del tempo su: verde su, giallo su in parte, rosso giù */
function UpStrip({ data, points, hover, onHover }) {
  const [ref, width] = useWidth()
  const start = new Date(data.start).getTime()
  const end = new Date(data.end).getTime()
  const step = data.step * 1000
  const plotW = width - PAD.left - PAD.right
  const x = (time) => PAD.left + ((time - start) / (end - start)) * plotW
  const w = Math.max(1, (step / (end - start)) * plotW) + 0.5  // un filo sovrapposti: niente righine tra i punti
  const tone = (up) => (up >= 0.999 ? 'up' : up > 0 ? 'partial' : 'down')
  return (
    <div className="port-chart" ref={ref}>
      <div className="port-chart__head">
        <h3>{t('Porta su')}</h3>
        {data.up !== null && <span className="muted">{t('su per il {p} del tempo', { p: percent(data.up, 2) })}</span>}
      </div>
      <svg width={width} height={22} className="port-chart__svg" shapeRendering="crispEdges" onMouseLeave={() => onHover(null)} role="img" aria-label={t('Porta su')}>
        {points.filter((p) => p.up !== null).map((p) => (
          <rect key={p.time} x={x(p.time)} width={w} y={2} height={16}
            className={`port-strip port-strip--${tone(p.up)}${hover === p.time ? ' port-strip--hover' : ''}`}
            onMouseEnter={() => onHover(p.time)}>
            <title>{`${when(p.time, data.period)}: ${percent(p.up)}`}</title>
          </rect>
        ))}
      </svg>
    </div>
  )
}

function StatsBody({ port, range, setRange }) {
  const { data, error, loading, reload } = useApi(`/interfaces/${port.id}/stats?range=${range}`)
  const [hover, setHover] = useState(null)
  useEffect(() => {
    const timer = setInterval(reload, 60000)
    return () => clearInterval(timer)
  }, [reload])

  const points = (data?.points || []).map((p) => ({ ...p, time: new Date(p.at).getTime(), bad: p.errors + p.discards }))
  const speed = data?.speed_mbps ? data.speed_mbps * 1e6 : null
  const usage = (bps) => (speed && bps !== null && bps !== undefined ? ` (${percent(bps / speed)})` : '')
  const hasTraffic = points.some((p) => p.in_bps !== null || p.out_bps !== null)
  const hasPoe = points.some((p) => p.poe_w !== null)
  const peakIn = Math.max(0, ...points.map((p) => p.in_peak_bps ?? p.in_bps ?? 0))
  const peakOut = Math.max(0, ...points.map((p) => p.out_peak_bps ?? p.out_bps ?? 0))
  const shared = { data, points, hover, onHover: setHover }

  return (
    <div className="port-stats">
      <div className="port-stats__bar">
        <div className="segmented" role="group" aria-label={t('Periodo')}>
          {RANGES.map((r) => (
            <button key={r.value} type="button" className={`segmented__item${range === r.value ? ' segmented__item--on' : ''}`}
              onClick={() => { setRange(r.value); setHover(null) }}>
              {r.label}
            </button>
          ))}
        </div>
        <span className="muted">
          {data && (data.period === '5m' ? t('un punto ogni 5 minuti') : data.period === '1h' ? t("un punto ogni ora") : t('un punto al giorno'))}
        </span>
      </div>
      <ErrorBox error={error} />
      {!data && loading && <Loading />}
      {data && (
        <>
          <dl className="port-stats__now">
            <div><dt>{t('Adesso in entrata')}</dt><dd>{formatBps(data.in_bps)}<span className="muted">{usage(data.in_bps)}</span></dd></div>
            <div><dt>{t('Adesso in uscita')}</dt><dd>{formatBps(data.out_bps)}<span className="muted">{usage(data.out_bps)}</span></dd></div>
            <div><dt>{t('Velocità della porta')}</dt><dd>{formatSpeed(data.speed_mbps)}</dd></div>
            <div><dt>{t('Ricevuti / inviati nel periodo')}</dt><dd>{formatBytes(data.in_octets)} / {formatBytes(data.out_octets)}</dd></div>
            <div><dt>{t('Picco nel periodo')}</dt><dd>{hasTraffic ? `${formatBps(peakIn)} / ${formatBps(peakOut)}` : '—'}</dd></div>
            <div><dt>{t('Errori / scarti nel periodo')}</dt><dd>{number(data.errors, 0)} / {number(data.discards, 0)}</dd></div>
          </dl>
          {points.length === 0 ? (
            <p className="empty">{t('Ancora nessun dato in questo periodo. Il monitor legge la porta ogni 5 minuti: il primo punto arriva dopo due letture.')}</p>
          ) : (
            <>
              {hasTraffic ? (
                <TimeChart {...shared} title={t('Traffico')} height={HEIGHT.traffic} format={(v) => formatBps(v)}
                  series={[
                    { key: 'in_bps', peak: 'in_peak_bps', label: t('In entrata'), className: 'tone-in', kind: 'area' },
                    { key: 'out_bps', peak: 'out_peak_bps', label: t('In uscita'), className: 'tone-out', kind: 'line' },
                  ]} />
              ) : (
                <p className="muted">{t('Lo switch non dà i contatori del traffico di questa porta.')}</p>
              )}
              <UpStrip {...shared} />
              {points.some((p) => p.bad) ? (
                <TimeChart {...shared} title={t('Errori e scarti')} height={HEIGHT.small} format={(v) => (v === null ? '—' : number(v, 0))}
                  series={[{ key: 'bad', label: t('Errori e scarti'), className: 'tone-bad', kind: 'bar' }]} />
              ) : (
                <p className="muted">{t('Nessun errore e nessun pacchetto scartato nel periodo.')}</p>
              )}
              {hasPoe && (
                <TimeChart {...shared} title={t('PoE')} height={HEIGHT.small} format={(v) => (v === null ? '—' : `${number(v)} W`)}
                  series={[{ key: 'poe_w', label: t('Potenza'), className: 'tone-poe', kind: 'line' }]} />
              )}
            </>
          )}
        </>
      )}
    </div>
  )
}

/** Finestra con lo storico di una porta, aperta dal pulsante del grafico nella tabella delle porte */
export default function PortStatsDialog({ port, device, onClose }) {
  const [range, setRange] = useState('1d')
  return (
    <Modal title={t('Storico di {port}', { port: port.name })} onClose={onClose} drawer wide>
      <div className="port-stats-wrap">
        <p className="muted port-stats__sub">{device} <Mono>{port.name}</Mono>{port.description ? ` · ${port.description}` : ''}</p>
        <StatsBody port={port} range={range} setRange={setRange} />
      </div>
    </Modal>
  )
}

/** Traffico di adesso, piccolo, sotto la velocità nella tabella delle porte */
export function PortRate({ port }) {
  if (port.in_bps === null || port.in_bps === undefined) return null
  return (
    <div className="port-rate muted" title={t('Traffico degli ultimi 5 minuti: in entrata / in uscita')}>
      ↓{formatBps(port.in_bps)} ↑{formatBps(port.out_bps)}
    </div>
  )
}
