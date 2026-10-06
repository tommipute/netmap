import { memo, useMemo } from 'react'
import { BaseEdge, getSmoothStepPath, useNodes } from '@xyflow/react'
import { roundedPath, routeOrthogonal } from './routing'

export const BUS_OFFSET = 28 // distanza della linea orizzontale comune dalla fila di device sotto
const RADIUS = 8

/**
 * Ostacoli per il cavo tra source e target: tutti i device, e le bolle dei rack in cui il cavo
 * non deve entrare (quelle che non contengono né la partenza né l'arrivo).
 */
function useObstacles(source, target) {
  const nodes = useNodes()
  return useMemo(
    () =>
      nodes
        .filter((n) => {
          if (n.type === 'device') return Boolean(n.measured?.width)
          return n.type === 'rack' && !n.data.ids.includes(source) && !n.data.ids.includes(target)
        })
        .map((n) => ({
          x: n.position.x,
          y: n.position.y,
          width: n.measured?.width ?? n.width,
          height: n.measured?.height ?? n.height,
        })),
    [nodes, source, target],
  )
}

/** Percorso semplice "a pettine", usato se il calcolo non trova strada. */
function simpleBus(sourceX, sourceY, targetX, targetY) {
  const busY = targetY - BUS_OFFSET
  return [
    { x: sourceX, y: sourceY },
    { x: sourceX, y: busY },
    { x: targetX, y: busY },
    { x: targetX, y: targetY },
  ]
}

/** Etichetta sul tratto finale, vicino al device di arrivo (non si sovrappone a quelle dei vicini). */
function labelPoint(points) {
  const end = points[points.length - 1]
  const before = points[points.length - 2]
  if (before && before.x === end.x && end.y - before.y >= BUS_OFFSET) return { x: end.x, y: end.y - BUS_OFFSET / 2 }
  // Altrimenti a metà del tratto più lungo
  let best = { len: -1, x: end.x, y: end.y }
  for (let k = 1; k < points.length; k++) {
    const a = points[k - 1]
    const b = points[k]
    const len = Math.abs(b.x - a.x) + Math.abs(b.y - a.y)
    if (len > best.len) best = { len, x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 }
  }
  return best
}

/**
 * Cavo ad angolo retto che gira attorno ai device (map/routing.js): scende dal device sopra, corre in
 * orizzontale preferibilmente appena sopra la fila del device collegato e scende su di lui.
 * Non passa sotto i device né dentro le bolle di altri rack.
 * I cavi verso la stessa fila condividono la linea orizzontale: 20 switch sul core diventano un albero ordinato.
 */
function BusEdge({ source, target, sourceX, sourceY, targetX, targetY, sourcePosition, targetPosition, style, label,
  labelStyle, labelShowBg, labelBgStyle, labelBgPadding, labelBgBorderRadius, interactionWidth }) {
  const rects = useObstacles(source, target)
  const { path, labelX, labelY } = useMemo(() => {
    const from = { x: sourceX, y: sourceY }
    const to = { x: targetX, y: targetY }
    let points = routeOrthogonal(from, to, rects, targetY - BUS_OFFSET)
    if (!points) {
      if (targetY - sourceY < BUS_OFFSET * 2) {
        const [p, x, y] = getSmoothStepPath({ sourceX, sourceY, targetX, targetY, sourcePosition, targetPosition, borderRadius: RADIUS })
        return { path: p, labelX: x, labelY: y }
      }
      points = simpleBus(sourceX, sourceY, targetX, targetY)
    }
    const at = labelPoint(points)
    return { path: roundedPath(points, RADIUS), labelX: at.x, labelY: at.y }
  }, [sourceX, sourceY, targetX, targetY, sourcePosition, targetPosition, rects])

  return (
    <BaseEdge path={path} style={style} label={label} labelX={labelX} labelY={labelY} labelStyle={labelStyle}
      labelShowBg={labelShowBg} labelBgStyle={labelBgStyle} labelBgPadding={labelBgPadding}
      labelBgBorderRadius={labelBgBorderRadius} interactionWidth={interactionWidth} />
  )
}

export default memo(BusEdge)
