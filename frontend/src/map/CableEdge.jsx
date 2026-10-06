import { memo } from 'react'
import { BaseEdge } from '@xyflow/react'
import { labelLength } from './geometry'
import { roundedPath } from './routing'

const RADIUS = 8
const LABEL_H = 16

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
 * Cavo tra due device. Percorso e nomi delle porte li calcola map/geometry.js per tutta la mappa
 * (data.geometry): qui si disegnano soltanto.
 */
function CableEdge({ data, style, interactionWidth }) {
  const geometry = data.geometry
  if (!geometry) return null
  return (
    <>
      <BaseEdge path={roundedPath(geometry.points, RADIUS)} style={style} interactionWidth={interactionWidth} />
      {geometry.labels.map((l, i) => <PortLabel key={i} {...l} />)}
    </>
  )
}

export default memo(CableEdge)
