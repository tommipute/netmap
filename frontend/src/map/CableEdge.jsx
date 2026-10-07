import { memo } from 'react'
import { BaseEdge, useReactFlow } from '@xyflow/react'
import { labelLength } from './geometry'
import { roundedPath } from './routing'

const RADIUS = 8
const LABEL_H = 16
const SNAP = 5 // i punti di ancoraggio si allineano a una griglia di 5 px

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
 * Maniglie del cavo selezionato: i punti di ancoraggio si trascinano (doppio clic = via), i "+" a metà dei tratti
 * aggiungono un punto. onRoute(punti) riceve i nuovi punti nel verso del cavo in mappa (source -> target).
 */
function RouteHandles({ edit, onRoute }) {
  const { screenToFlowPosition } = useReactFlow()

  const drag = (event, corners, index) => {
    event.preventDefault()
    event.stopPropagation()
    const move = (e) => {
      const next = [...corners]
      next[index] = snap(screenToFlowPosition({ x: e.clientX, y: e.clientY }))
      onRoute(next)
    }
    const stop = () => {
      window.removeEventListener('pointermove', move)
      window.removeEventListener('pointerup', stop)
    }
    window.addEventListener('pointermove', move)
    window.addEventListener('pointerup', stop)
  }

  return (
    <g className="cable-handles nodrag nopan">
      {edit.inserts.map((h) => (
        <g key={`i${h.index}-${h.x}-${h.y}`} className="cable-handle cable-handle--add" transform={`translate(${h.x} ${h.y})`}
          onPointerDown={(e) => {
            // Il nuovo punto nasce dove si è cliccato e si trascina subito
            const corners = [...edit.corners]
            corners.splice(h.index, 0, snap({ x: h.x, y: h.y }))
            onRoute(corners)
            drag(e, corners, h.index)
          }}>
          <title>Trascina per aggiungere un punto di ancoraggio</title>
          <circle r={6} />
          <path d="M -3 0 H 3 M 0 -3 V 3" />
        </g>
      ))}
      {edit.corners.map((c, i) => (
        <circle key={`c${i}`} className="cable-handle cable-handle--point" cx={c.x} cy={c.y} r={5}
          onPointerDown={(e) => drag(e, edit.corners, i)}
          onDoubleClick={(e) => {
            e.stopPropagation()
            onRoute(edit.corners.filter((_, k) => k !== i))
          }}>
          <title>Trascina per spostare il cavo, doppio clic per togliere il punto</title>
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
