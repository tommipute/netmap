import { memo } from 'react'
import { BaseEdge, getSmoothStepPath } from '@xyflow/react'

export const BUS_OFFSET = 28 // distanza della linea orizzontale dalla fila di device sotto
const RADIUS = 8

/**
 * Cavo ad angolo "a pettine": scende dal device sopra, corre in orizzontale appena sopra la fila
 * del device collegato e scende su di lui. I cavi verso la stessa fila condividono la linea orizzontale,
 * così 20 switch attaccati al core diventano un albero ordinato invece di una raggiera.
 * Se il device collegato non sta sotto (stessa fila o più in alto) uso il percorso a gradini di React Flow.
 */
function BusEdge({ sourceX, sourceY, targetX, targetY, sourcePosition, targetPosition, style, label,
  labelStyle, labelShowBg, labelBgStyle, labelBgPadding, labelBgBorderRadius, interactionWidth }) {
  let path
  let labelX
  let labelY
  if (targetY - sourceY < BUS_OFFSET * 2) {
    ;[path, labelX, labelY] = getSmoothStepPath({ sourceX, sourceY, targetX, targetY, sourcePosition, targetPosition, borderRadius: RADIUS })
  } else {
    const busY = targetY - BUS_OFFSET
    const dx = targetX - sourceX
    const r = Math.min(RADIUS, Math.abs(dx) / 2, (busY - sourceY) / 2)
    const dir = Math.sign(dx)
    path = Math.abs(dx) < 1
      ? `M ${sourceX} ${sourceY} L ${targetX} ${targetY}`
      : [
          `M ${sourceX} ${sourceY}`,
          `L ${sourceX} ${busY - r}`,
          `Q ${sourceX} ${busY} ${sourceX + dir * r} ${busY}`,
          `L ${targetX - dir * r} ${busY}`,
          `Q ${targetX} ${busY} ${targetX} ${busY + r}`,
          `L ${targetX} ${targetY}`,
        ].join(' ')
    // Etichetta sul tratto finale, vicino al device: non si sovrappone a quelle dei vicini
    labelX = targetX
    labelY = busY + BUS_OFFSET / 2
  }
  return (
    <BaseEdge path={path} style={style} label={label} labelX={labelX} labelY={labelY} labelStyle={labelStyle}
      labelShowBg={labelShowBg} labelBgStyle={labelBgStyle} labelBgPadding={labelBgPadding}
      labelBgBorderRadius={labelBgBorderRadius} interactionWidth={interactionWidth} />
  )
}

export default memo(BusEdge)
