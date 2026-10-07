import { memo } from 'react'
import { BaseEdge, useReactFlow } from '@xyflow/react'
import { endOnRect, labelLength, moveSegment } from './geometry'
import { roundedPath } from './routing'

const RADIUS = 8
const LABEL_H = 16
const SNAP = 5 // i tratti spostati a mano si allineano a una griglia di 5 px

const snap = (p) => ({ x: Math.round(p.x / SNAP) * SNAP, y: Math.round(p.y / SNAP) * SNAP })

/** Nome di una porta: riquadro con il testo, ruotato se il cavo esce da sopra o da sotto il device. */
function PortLabel({ x, y, text, vertical }) {
  const width = labelLength(text)
  return (
    <g className="port-label" transform={`translate(${x} ${y})${vertical ? ' rotate(-90)' : ''}`}>
      <rect className="react-flow__edge-textbg" x={-width / 2} y={-LABEL_H / 2} width={width} height={LABEL_H} rx={3} />
      <text className="react-flow__edge-text" textAnchor="middle" dominantBaseline="central">{text}</text>
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
            <title>Trascina per spostare questo tratto del cavo</title>
          </rect>
        )
      })}
      {edit.ends.filter((end) => end.rect).map((end) => (
        <circle key={end.end} className="cable-handle cable-handle--end" cx={end.x} cy={end.y} r={4.5}
          onPointerDown={(e) => drag(e, (p) => onRoute({ [`${end.end}End`]: endOnRect(end.rect, p) }))}>
          <title>Trascina lungo il bordo del device per spostare dove si attacca il cavo</title>
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
      {geometry.labels.map((l, i) => <PortLabel key={i} {...l} />)}
      {data.onRoute && geometry.edit && <RouteHandles edit={geometry.edit} onRoute={data.onRoute} />}
    </>
  )
}

export default memo(CableEdge)
