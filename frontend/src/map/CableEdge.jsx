import { memo } from 'react'
import { BaseEdge, EdgeText } from '@xyflow/react'
import { roundedPath } from './routing'

const RADIUS = 8

/**
 * Cavo tra due device. Percorso ed etichette delle porte li calcola map/geometry.js per tutta la mappa
 * (data.geometry): qui si disegnano soltanto.
 */
function CableEdge({ data, style, labelStyle, labelBgPadding, labelBgBorderRadius, interactionWidth }) {
  const geometry = data.geometry
  if (!geometry) return null
  return (
    <>
      <BaseEdge path={roundedPath(geometry.points, RADIUS)} style={style} interactionWidth={interactionWidth} />
      {geometry.labels.map((l) => (
        <EdgeText key={l.text} x={l.x} y={l.y} label={l.text} labelStyle={labelStyle} labelShowBg
          labelBgPadding={labelBgPadding} labelBgBorderRadius={labelBgBorderRadius} />
      ))}
    </>
  )
}

export default memo(CableEdge)
