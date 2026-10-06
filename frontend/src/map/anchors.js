/**
 * Punti di attacco dei cavi sui device.
 *
 * Per ogni cavo scelgo i lati che si guardano: sotto→sopra se l'altro device sta più in basso, sopra→sotto se
 * sta più in alto, destra↔sinistra se sono affiancati. Su ogni lato i cavi dello stesso tipo partono dallo stesso
 * punto e si uniscono (il core con 20 switch in fibra resta un albero ordinato); cavi di tipo diverso partono da
 * punti diversi, distribuiti lungo il bordo in ordine di posizione dell'altro capo (così non si incrociano).
 * Due cavi verso lo stesso device (es. un LAG) non si uniscono mai: sembrerebbero uno solo.
 */
const MIN_GAP = 24 // sotto questa distanza verticale due device si considerano affiancati
const STRAIGHT_INSET = 12 // un cavo raddrizzato resta almeno a questa distanza dagli angoli

export const OUTWARD = { top: { x: 0, y: -1 }, bottom: { x: 0, y: 1 }, left: { x: -1, y: 0 }, right: { x: 1, y: 0 } }

export function rectOf(node) {
  if (!node?.measured?.width) return null
  return { x: node.position.x, y: node.position.y, w: node.measured.width, h: node.measured.height }
}

const center = (r) => ({ x: r.x + r.w / 2, y: r.y + r.h / 2 })

/** Lati da usare per un cavo da a verso b. */
export function chooseSides(a, b) {
  if (b.y - (a.y + a.h) >= MIN_GAP) return ['bottom', 'top']
  if (a.y - (b.y + b.h) >= MIN_GAP) return ['top', 'bottom']
  const right = b.x - (a.x + a.w)
  const left = a.x - (b.x + b.w)
  if (right < 0 && left < 0) return center(b).y >= center(a).y ? ['bottom', 'top'] : ['top', 'bottom']
  return right >= left ? ['right', 'left'] : ['left', 'right']
}

function pointOn(r, side, f) {
  switch (side) {
    case 'top':
      return { x: r.x + r.w * f, y: r.y }
    case 'bottom':
      return { x: r.x + r.w * f, y: r.y + r.h }
    case 'left':
      return { x: r.x, y: r.y + r.h * f }
    default:
      return { x: r.x + r.w, y: r.y + r.h * f }
  }
}

/**
 * nodes: nodi React Flow dei device (misurati), edges: [{ id, source, target, data: { type } }].
 * Restituisce { [edgeId]: { source: { x, y, side, shared }, target: { ... } } }; i cavi tra device non ancora
 * misurati mancano. shared = il punto è in comune con altri cavi.
 */
export function assignAnchors(nodes, edges) {
  const rects = new Map()
  for (const n of nodes) {
    const r = rectOf(n)
    if (r) rects.set(n.id, r)
  }
  const sides = new Map() // "nodo|lato" -> [{ edgeId, end, kind, otherId, other }]
  const result = {}
  for (const e of edges) {
    const a = rects.get(e.source)
    const b = rects.get(e.target)
    if (!a || !b) continue
    const [sa, sb] = chooseSides(a, b)
    result[e.id] = { source: { side: sa }, target: { side: sb } }
    const kind = e.data?.type || ''
    for (const [nodeId, side, end, otherId, other] of [[e.source, sa, 'source', e.target, b], [e.target, sb, 'target', e.source, a]]) {
      const key = `${nodeId}|${side}`
      if (!sides.has(key)) sides.set(key, [])
      sides.get(key).push({ edgeId: e.id, end, kind, otherId, other: center(other) })
    }
  }
  for (const [key, list] of sides) {
    const [nodeId, side] = key.split('|')
    const r = rects.get(nodeId)
    const axis = side === 'top' || side === 'bottom' ? 'x' : 'y'
    // Punti condivisi: stesso tipo di cavo, mai due cavi verso lo stesso device nello stesso punto
    const slots = []
    for (const item of list) {
      let slot = slots.find((s) => s.kind === item.kind && !s.others.has(item.otherId))
      if (!slot) {
        slot = { kind: item.kind, others: new Set(), items: [] }
        slots.push(slot)
      }
      slot.others.add(item.otherId)
      slot.items.push(item)
    }
    const position = (slot) => slot.items.reduce((sum, it) => sum + it.other[axis], 0) / slot.items.length
    slots.sort((p, q) => position(p) - position(q) || p.kind.localeCompare(q.kind))
    slots.forEach((slot, i) => {
      const point = pointOn(r, side, (i + 1) / (slots.length + 1))
      for (const item of slot.items) {
        Object.assign(result[item.edgeId][item.end], point, {
          shared: slot.items.length > 1,
          alone: slots.length === 1 && slot.items.length === 1,
        })
      }
    })
  }
  // Un solo cavo tra due lati che si guardano: se i device sono quasi allineati lo raddrizzo (niente scalini)
  for (const e of edges) {
    const anchor = result[e.id]
    if (!anchor || !anchor.source.alone || !anchor.target.alone) continue
    const a = rects.get(e.source)
    const b = rects.get(e.target)
    const vertical = anchor.source.side === 'bottom' || anchor.source.side === 'top'
    const [axis, lo, hi] = vertical
      ? ['x', Math.max(a.x, b.x) + STRAIGHT_INSET, Math.min(a.x + a.w, b.x + b.w) - STRAIGHT_INSET]
      : ['y', Math.max(a.y, b.y) + STRAIGHT_INSET, Math.min(a.y + a.h, b.y + b.h) - STRAIGHT_INSET]
    const middle = (anchor.source[axis] + anchor.target[axis]) / 2
    if (lo <= hi) {
      const value = Math.min(hi, Math.max(lo, middle))
      anchor.source[axis] = value
      anchor.target[axis] = value
    }
  }
  return result
}
