/**
 * Punti di attacco dei cavi sui device.
 *
 * Per ogni cavo scelgo i lati che si guardano: sotto→sopra se l'altro device sta più in basso, sopra→sotto se
 * sta più in alto, destra↔sinistra se sono affiancati. Su ogni lato i cavi dello stesso tipo partono dallo stesso
 * punto e si uniscono (il core con 20 switch in fibra resta un albero ordinato); cavi di tipo diverso partono da
 * punti diversi, distribuiti lungo il bordo in ordine di posizione dell'altro capo (così non si incrociano).
 * Due cavi verso lo stesso device (es. un LAG) non si uniscono mai: sembrerebbero uno solo.
 * Con separate (nomi delle porte visibili) ogni cavo ha il suo punto: ogni porta ha il suo posto per il nome.
 * Un cavo con il percorso sistemato a mano (data.waypoints = spigoli) esce dal lato rivolto verso il suo primo
 * spigolo ed entra da quello rivolto verso l'ultimo. Un'estremità spostata a mano (data.sourceEnd/targetEnd =
 * { side, f }) resta lì: non entra nella distribuzione dei punti sul lato.
 */
const MIN_GAP = 24 // sotto questa distanza verticale due device si considerano affiancati
const STRAIGHT_INSET = 12 // un cavo raddrizzato resta almeno a questa distanza dagli angoli
const JOG = 24 // sotto questa differenza tra i due capi il cavo si raddrizza
const MIN_SEP = 18 // distanza minima tra due capi sullo stesso lato (spazio per i nomi delle porte)
const CLEARANCE = 90 // spazio libero che serve sopra/sotto un device per far uscire un cavo (e il nome della porta)

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

export function pointOn(r, side, f) {
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

/** Lato di r rivolto verso il punto p (punti di ancoraggio): sotto/sopra se p sta più in basso/in alto, se no di lato. */
function sideToward(r, p) {
  if (p.y >= r.y + r.h) return 'bottom'
  if (p.y <= r.y) return 'top'
  return p.x >= r.x + r.w / 2 ? 'right' : 'left'
}

/** Lato sopra/sotto di un device coperto da un altro device vicino (non l'altro capo del cavo) -> lato sinistro/destro. */
function sideIfBlocked(rects, ownId, otherId, side) {
  if (side !== 'top' && side !== 'bottom') return side
  const r = rects.get(ownId)
  const blocked = [...rects].some(([id, o]) => {
    if (id === ownId || id === otherId) return false
    const overlapX = o.x < r.x + r.w && o.x + o.w > r.x
    const gap = side === 'bottom' ? o.y - (r.y + r.h) : r.y - (o.y + o.h)
    return overlapX && gap >= 0 && gap < CLEARANCE
  })
  if (!blocked) return side
  return center(rects.get(otherId)).x < center(r).x ? 'left' : 'right'
}

/**
 * nodes: nodi React Flow dei device (misurati), edges: [{ id, source, target, data: { type } }].
 * Restituisce { [edgeId]: { source: { x, y, side, shared }, target: { ... } } }; i cavi tra device non ancora
 * misurati mancano. shared = il punto è in comune con altri cavi.
 */
export function assignAnchors(nodes, edges, { separate = false } = {}) {
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
    const waypoints = e.data?.waypoints
    let sa, sb, towardA, towardB
    if (waypoints?.length) {
      towardA = waypoints[0]
      towardB = waypoints[waypoints.length - 1]
      sa = sideToward(a, towardA)
      sb = sideToward(b, towardB)
    } else {
      ;[sa, sb] = chooseSides(a, b)
      // Sopra/sotto c'è subito un altro device (es. impilati nello stesso rack): il cavo esce di lato, verso l'altro capo
      sa = sideIfBlocked(rects, e.source, e.target, sa)
      sb = sideIfBlocked(rects, e.target, e.source, sb)
      towardA = center(b)
      towardB = center(a)
    }
    const fixedA = e.data?.sourceEnd
    const fixedB = e.data?.targetEnd
    result[e.id] = {
      source: fixedA ? { ...pointOn(a, fixedA.side, fixedA.f), side: fixedA.side, fixed: true } : { side: sa },
      target: fixedB ? { ...pointOn(b, fixedB.side, fixedB.f), side: fixedB.side, fixed: true } : { side: sb },
    }
    const kind = e.data?.type || ''
    for (const [nodeId, side, end, otherId, other] of [[e.source, sa, 'source', e.target, towardA], [e.target, sb, 'target', e.source, towardB]]) {
      if (result[e.id][end].fixed) continue
      const key = `${nodeId}|${side}`
      if (!sides.has(key)) sides.set(key, [])
      sides.get(key).push({ edgeId: e.id, end, kind, otherId, other })
    }
  }
  for (const [key, list] of sides) {
    const [nodeId, side] = key.split('|')
    const r = rects.get(nodeId)
    const axis = side === 'top' || side === 'bottom' ? 'x' : 'y'
    // Punti condivisi: stesso tipo di cavo, mai due cavi verso lo stesso device nello stesso punto
    const slots = []
    for (const item of list) {
      let slot = separate ? null : slots.find((s) => s.kind === item.kind && !s.others.has(item.otherId))
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
  // Cavi tra due lati che si guardano con i capi quasi allineati: li raddrizzo, niente scalini di pochi pixel.
  // Se è l'unico cavo su tutti e due i lati sposto entrambi i capi (anche molto, purché dentro i due device);
  // altrimenti sposto un capo solo, quello con più spazio, se resta lontano dagli altri cavi del suo lato.
  const positionsOn = (nodeId, side, skipEdge) =>
    (sides.get(`${nodeId}|${side}`) || []).filter((it) => it.edgeId !== skipEdge).map((it) => result[it.edgeId][it.end])
  for (const e of edges) {
    const anchor = result[e.id]
    if (!anchor || e.data?.waypoints?.length || anchor.source.fixed || anchor.target.fixed) continue
    const { source, target } = anchor
    if (OUTWARD[source.side].x !== -OUTWARD[target.side].x || OUTWARD[source.side].y !== -OUTWARD[target.side].y) continue
    const a = rects.get(e.source)
    const b = rects.get(e.target)
    const vertical = source.side === 'bottom' || source.side === 'top'
    const axis = vertical ? 'x' : 'y'
    const range = (r) => (vertical ? [r.x + STRAIGHT_INSET, r.x + r.w - STRAIGHT_INSET] : [r.y + STRAIGHT_INSET, r.y + r.h - STRAIGHT_INSET])
    if (source.alone && target.alone) {
      const lo = Math.max(range(a)[0], range(b)[0])
      const hi = Math.min(range(a)[1], range(b)[1])
      if (lo <= hi) {
        const value = Math.min(hi, Math.max(lo, (source[axis] + target[axis]) / 2))
        source[axis] = value
        target[axis] = value
      }
      continue
    }
    const delta = Math.abs(target[axis] - source[axis])
    if (delta < 0.5 || delta >= JOG) continue
    const candidates = [
      { end: source, value: target[axis], r: a, others: positionsOn(e.source, source.side, e.id) },
      { end: target, value: source[axis], r: b, others: positionsOn(e.target, target.side, e.id) },
    ].sort((p, q) => p.others.length - q.others.length)
    for (const c of candidates) {
      const [lo, hi] = range(c.r)
      if (c.end.shared || c.value < lo || c.value > hi) continue
      if (c.others.some((o) => Math.abs(o[axis] - c.value) < MIN_SEP)) continue
      c.end[axis] = c.value
      break
    }
  }
  return result
}
