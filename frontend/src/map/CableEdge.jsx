import { memo } from 'react'
import { BaseEdge, useReactFlow } from '@xyflow/react'
import { OUTWARD } from './anchors'
import { PLUG, endOnRect, labelLength, moveSegment } from './geometry'
import { roundedPath } from './routing'
import { t } from '../i18n'

const RADIUS = 8
const LABEL_H = 16
const SNAP = 5 // i tratti spostati a mano si allineano a una griglia di 5 px

const snap = (p) => ({ x: Math.round(p.x / SNAP) * SNAP, y: Math.round(p.y / SNAP) * SNAP })

/** Nome di una porta: riquadro con il testo, ruotato se il cavo esce da sopra o da sotto il device. */
function PortLabel({ x, y, text, title, vertical }) {
  const width = labelLength(text)
  return (
    <g className="port-label" transform={`translate(${x} ${y})${vertical ? ' rotate(-90)' : ''}`}>
      {title && title !== text && <title>{title}</title>}
      <rect className="react-flow__edge-textbg" x={-width / 2} y={-LABEL_H / 2} width={width} height={LABEL_H} rx={3} />
      <text className="react-flow__edge-text" textAnchor="middle" dominantBaseline="central">{text}</text>
    </g>
  )
}

const PLUG_W = 12

/**
 * Connettore stilizzato dove il cavo entra nel device (corpo del colore del cavo e linguetta più chiara):
 * così si vede dove il cavo è collegato e dove invece passa soltanto vicino.
 */
function Plug({ x, y, side, color }) {
  const o = OUTWARD[side]
  const vertical = o.y !== 0
  const w = vertical ? PLUG_W : PLUG
  const h = vertical ? PLUG : PLUG_W
  // Il connettore sta fuori dal device, appoggiato al bordo
  const left = vertical ? x - w / 2 : o.x > 0 ? x : x - w
  const top = vertical ? (o.y > 0 ? y : y - h) : y - h / 2
  return (
    <g className="cable-plug">
      <rect x={left} y={top} width={w} height={h} rx={1.5} style={{ fill: color }} />
      <rect className="cable-plug__tab" x={vertical ? x - 2 : left + (o.x > 0 ? 2.5 : w - 4.5)} y={vertical ? top + (o.y > 0 ? 2.5 : h - 4.5) : y - 2}
        width={vertical ? 4 : 2} height={vertical ? 2 : 4} />
    </g>
  )
}

/**
 * Maniglie del cavo selezionato: una barretta su ogni tratto che si può spostare (solo di traverso, il cavo resta
 * ad angolo retto) e un pallino su ogni estremità, da far scorrere lungo il bordo del device (anche su un altro lato).
 * onRoute({ points } | { sourceEnd } | { targetEnd }) riceve le modifiche nel verso del cavo in mappa.
 */
function RouteHandles({ edit, onRoute }) {
  const { screenToFlowPosition } = useReactFlow()

  const drag = (event, onMove) => {
    event.preventDefault()
    event.stopPropagation()
    const move = (e) => onMove(snap(screenToFlowPosition({ x: e.clientX, y: e.clientY })))
    const stop = () => {
      window.removeEventListener('pointermove', move)
      window.removeEventListener('pointerup', stop)
      // Il clic che chiude il trascinamento non deve arrivare alla mappa (deselezionerebbe il cavo)
      const swallow = (e) => e.stopPropagation()
      window.addEventListener('click', swallow, { capture: true, once: true })
      setTimeout(() => window.removeEventListener('click', swallow, { capture: true }), 0)
    }
    window.addEventListener('pointermove', move)
    window.addEventListener('pointerup', stop)
  }

  return (
    <g className="cable-handles nodrag nopan">
      {edit.segments.map((s) => {
        const horizontal = s.axis === 'y'
        return (
          <rect key={`s${s.index}`} className={`cable-handle cable-handle--segment cable-handle--${horizontal ? 'ns' : 'ew'}`}
            x={s.x - (horizontal ? 9 : 3)} y={s.y - (horizontal ? 3 : 9)} width={horizontal ? 18 : 6} height={horizontal ? 6 : 18} rx={3}
            onPointerDown={(e) => drag(e, (p) => onRoute({ points: moveSegment(edit, s.index, p[s.axis]) }))}>
            <title>{t('Trascina per spostare questo tratto del cavo')}</title>
          </rect>
        )
      })}
      {edit.ends.filter((end) => end.rect).map((end) => (
        <circle key={end.end} className="cable-handle cable-handle--end" cx={end.x} cy={end.y} r={4.5}
          onPointerDown={(e) => drag(e, (p) => onRoute({ [`${end.end}End`]: endOnRect(end.rect, p) }))}>
          <title>{t('Trascina lungo il bordo del device per spostare dove si attacca il cavo')}</title>
        </circle>
      ))}
    </g>
  )
}

/**
 * Cavo tra due device. Percorso e nomi delle porte li calcola map/geometry.js per tutta la mappa
 * (data.geometry): qui si disegnano soltanto, più le maniglie se il cavo selezionato si può modificare.
 */
function CableEdge({ data, style, interactionWidth }) {
  const geometry = data.geometry
  if (!geometry) return null
  return (
    <>
      <BaseEdge path={roundedPath(geometry.points, RADIUS)} style={style} interactionWidth={interactionWidth} />
      {geometry.ends.map((end, i) => <Plug key={i} {...end} color={style?.stroke} />)}
      {geometry.labels.map((l, i) => <PortLabel key={i} {...l} />)}
      {data.onRoute && geometry.edit && <RouteHandles edit={geometry.edit} onRoute={data.onRoute} />}
    </>
  )
}

export default memo(CableEdge)
