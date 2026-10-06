/**
 * Geometria di tutti i cavi di una mappa, calcolata in un punto solo (MapEditor) perché le etichette
 * delle porte devono conoscere quelle degli altri cavi per non sovrapporsi.
 *
 * 1. punti di attacco (anchors.js), 2. percorso di ogni cavo (routing.js, oppure linea dritta),
 * 3. etichette: una per cavo, "Gi1/0/1 – 49" (porta di partenza – porta di arrivo), una alla volta dai cavi più
 *    corti (hanno meno posto): dal centro del cavo verso le estremità, sulla linea o appena accanto, prima fuori
 *    dal tratto che il cavo condivide con altri. Non si sovrappone a device e altre etichette; se non c'è nessun
 *    posto libero si accetta di toccare un'altra etichetta, mai un device (sotto un device non si leggerebbe).
 */
import { OUTWARD, assignAnchors, rectOf } from './anchors'
import { MARGIN, STUB, routeOrthogonal } from './routing'

export const BUS_OFFSET = 28 // riga orizzontale preferita: questa distanza sopra (o sotto) il device di arrivo
const LABEL_H = 16
const LABEL_FROM_END = 12 // prima posizione provata: distanza dal bordo del device
const LABEL_STEP = 8
const CHAR_W = 6.6 // font mono 11 px
const labelWidth = (text) => String(text).length * CHAR_W + 12

/** Distanza tra due lati che si guardano (null se non si guardano). */
function facingGap(from, to) {
  const out = OUTWARD[from.side]
  if (out.x !== -OUTWARD[to.side].x || out.y !== -OUTWARD[to.side].y) return null
  const gap = out.x ? (to.x - from.x) * out.x : (to.y - from.y) * out.y
  return gap > 0 ? gap : null
}

/** Tratto dritto alle estremità: più corto se i due lati si guardano da vicino (niente anelli). */
function stubFor(from, to) {
  const gap = facingGap(from, to)
  return gap === null ? STUB : Math.max(3, Math.min(STUB, gap / 2 - 1))
}

/** Percorso di riserva se la ricerca non trova strada: esce, una curva a metà, entra. */
function fallback(from, to, stub) {
  const a = { x: from.x + OUTWARD[from.side].x * stub, y: from.y + OUTWARD[from.side].y * stub }
  const b = { x: to.x + OUTWARD[to.side].x * stub, y: to.y + OUTWARD[to.side].y * stub }
  const mid = OUTWARD[from.side].y !== 0
    ? [{ x: a.x, y: (a.y + b.y) / 2 }, { x: b.x, y: (a.y + b.y) / 2 }]
    : [{ x: (a.x + b.x) / 2, y: a.y }, { x: (a.x + b.x) / 2, y: b.y }]
  return [from, a, ...mid, b, to]
}

// ---------------------------------------------------------------- polilinee
function segments(points) {
  const out = []
  for (let k = 1; k < points.length; k++) {
    const a = points[k - 1]
    const b = points[k]
    out.push({ a, b, len: Math.abs(b.x - a.x) + Math.abs(b.y - a.y) })
  }
  return out
}
const lengthOf = (points) => segments(points).reduce((sum, s) => sum + s.len, 0)

function pointAt(points, distance) {
  let left = distance
  for (const s of segments(points)) {
    if (left <= s.len) {
      const t = s.len ? left / s.len : 0
      return { x: s.a.x + (s.b.x - s.a.x) * t, y: s.a.y + (s.b.y - s.a.y) * t }
    }
    left -= s.len
  }
  return points[points.length - 1]
}

/** Lunghezza del tratto iniziale in comune tra due percorsi che partono dallo stesso punto. */
function commonPrefix(p, q) {
  const sp = segments(p)
  const sq = segments(q)
  let total = 0
  for (let k = 0; k < Math.min(sp.length, sq.length); k++) {
    const a = sp[k]
    const b = sq[k]
    const same = a.a.x === b.a.x && a.a.y === b.a.y
    const dirA = { x: Math.sign(a.b.x - a.a.x), y: Math.sign(a.b.y - a.a.y) }
    const dirB = { x: Math.sign(b.b.x - b.a.x), y: Math.sign(b.b.y - b.a.y) }
    if (!same || dirA.x !== dirB.x || dirA.y !== dirB.y) break
    total += Math.min(a.len, b.len)
    if (a.len !== b.len) break
  }
  return total
}

const reversed = (points) => [...points].reverse()

// ---------------------------------------------------------------- etichette
function boxAt(point, text) {
  const w = labelWidth(text)
  return { l: point.x - w / 2, r: point.x + w / 2, t: point.y - LABEL_H / 2, b: point.y + LABEL_H / 2 }
}
const hit = (a, b) => a.l < b.r && a.r > b.l && a.t < b.b && a.b > b.t

/**
 * Posto libero per l'etichetta tra le distanze lo e hi lungo il percorso, partendo da start (il centro) e
 * allontanandosi: prima sulla linea, poi appena accanto (sopra/sotto un tratto orizzontale, a lato di uno verticale).
 */
function findLabelSpot(points, text, start, lo, hi, isFree) {
  if (hi < lo) return null
  const width = labelWidth(text)
  for (let k = 0; start - k * LABEL_STEP >= lo || start + k * LABEL_STEP <= hi; k++) {
    for (const d of k ? [start + k * LABEL_STEP, start - k * LABEL_STEP] : [Math.min(hi, Math.max(lo, start))]) {
      if (d < lo || d > hi) continue
      const point = pointAt(points, d)
      const ahead = pointAt(points, Math.min(d + 1, lengthOf(points)))
      const horizontal = Math.abs(ahead.x - point.x) >= Math.abs(ahead.y - point.y)
      // Sulla linea, poi sempre più lontano ai due lati (tra due device vicini l'etichetta sale sopra di loro)
      const unit = horizontal ? { x: 0, y: 1 } : { x: 1, y: 0 }
      const first = horizontal ? LABEL_H / 2 + 3 : width / 2 + 3
      const offsets = [0, ...[0, 1, 2, 3, 4, 5].flatMap((i) => [-(first + i * 10), first + i * 10])]
      for (const offset of offsets) {
        const candidate = { x: point.x + unit.x * offset, y: point.y + unit.y * offset }
        const box = boxAt(candidate, text)
        if (isFree(box)) return { point: candidate, box }
      }
    }
  }
  return null
}

/**
 * nodes: device (nodi React Flow misurati), bubbles: bolle dei rack, edges: cavi React Flow con
 * data.type, data.sourceLabel, data.targetLabel. mode: 'bus' (ad angolo) o 'straight'.
 * Restituisce { [edgeId]: { points, labels: [{ x, y, text }] } }.
 */
export function cableGeometry(nodes, bubbles, edges, mode) {
  const anchors = assignAnchors(nodes, edges)
  const devices = nodes.map((n) => ({ id: n.id, r: rectOf(n) })).filter((d) => d.r)
  const result = {}

  for (const e of edges) {
    const anchor = anchors[e.id]
    if (!anchor) continue
    const from = anchor.source
    const to = anchor.target
    const stub = stubFor(from, to)
    let points
    if (mode === 'bus') {
      const endMargin = Math.max(1, stub - 1)
      const obstacles = [
        ...devices.map((d) => ({
          x: d.r.x, y: d.r.y, width: d.r.w, height: d.r.h,
          margin: d.id === e.source || d.id === e.target ? endMargin : MARGIN,
        })),
        // Bolle dei rack in cui il cavo non deve entrare: quelle senza la partenza né l'arrivo
        ...bubbles
          .filter((b) => !b.data.ids.includes(e.source) && !b.data.ids.includes(e.target))
          .map((b) => ({ x: b.position.x, y: b.position.y, width: b.width, height: b.height })),
      ]
      const preferY = to.side === 'top' ? to.y - BUS_OFFSET : to.side === 'bottom' ? to.y + BUS_OFFSET : undefined
      points = routeOrthogonal(from, to, obstacles, { preferY, stub }) || fallback(from, to, stub)
    } else {
      points = [{ x: from.x, y: from.y }, { x: to.x, y: to.y }]
    }
    result[e.id] = { points, labels: [] }
  }

  // Tratto condiviso a ogni estremità: con i cavi che partono dallo stesso punto dello stesso device
  const byPoint = new Map()
  for (const e of edges) {
    if (!result[e.id]) continue
    for (const end of ['source', 'target']) {
      const a = anchors[e.id][end]
      const key = `${e[end]}|${a.x}|${a.y}`
      if (!byPoint.has(key)) byPoint.set(key, [])
      byPoint.get(key).push({ id: e.id, end })
    }
  }
  const sharedFrom = {} // { edgeId: { source: lunghezza, target: lunghezza } }
  for (const group of byPoint.values()) {
    for (const item of group) {
      const own = result[item.id].points
      const path = item.end === 'source' ? own : reversed(own)
      let longest = 0
      for (const other of group) {
        if (other === item) continue
        const op = result[other.id].points
        longest = Math.max(longest, commonPrefix(path, other.end === 'source' ? op : reversed(op)))
      }
      sharedFrom[item.id] = { ...sharedFrom[item.id], [item.end]: longest }
    }
  }

  // Etichette: prima i cavi più corti
  const placed = devices.map((d) => ({ l: d.r.x - 2, r: d.r.x + d.r.w + 2, t: d.r.y - 2, b: d.r.y + d.r.h + 2 }))
  // Anche il nome del rack in basso a sinistra nella bolla ("Rack R01", vedi RackNode)
  for (const bubble of bubbles) {
    const bottom = bubble.position.y + bubble.height
    const width = (String(bubble.data.name).length + 5) * 7 + 12
    placed.push({ l: bubble.position.x + 8, r: bubble.position.x + 8 + width, t: bottom - 24, b: bottom - 2 })
  }
  const deviceBoxes = placed.length
  const isFree = (box) => !placed.some((p) => hit(p, box))
  const clearOfDevices = (box) => !placed.slice(0, deviceBoxes).some((p) => hit(p, box))
  const order = edges
    .filter((e) => result[e.id] && e.data?.sourceLabel && e.data?.targetLabel)
    .sort((a, b) => lengthOf(result[a.id].points) - lengthOf(result[b.id].points))
  for (const e of order) {
    const { points } = result[e.id]
    const text = `${e.data.sourceLabel} – ${e.data.targetLabel}`
    const total = lengthOf(points)
    const shared = sharedFrom[e.id] || {}
    const half = total / 2
    // Prima nella parte che il cavo non condivide con altri (lì si capisce di chi è), poi ovunque sul cavo
    const spot =
      findLabelSpot(points, text, half, (shared.source || 0) + LABEL_FROM_END, total - (shared.target || 0) - LABEL_FROM_END, isFree) ||
      findLabelSpot(points, text, half, LABEL_FROM_END, total - LABEL_FROM_END, isFree)
    // Mai nascosta: senza un posto libero almeno fuori dai device (sotto un device non si leggerebbe),
    // altrimenti a metà cavo
    const fallback = spot || findLabelSpot(points, text, half, LABEL_FROM_END, total - LABEL_FROM_END, clearOfDevices)
    const point = fallback ? fallback.point : pointAt(points, half)
    placed.push(fallback ? fallback.box : boxAt(point, text))
    result[e.id].labels = [{ ...point, text }]
  }
  return result
}
