/**
 * Percorso ad angolo retto che non passa sotto i device.
 * Parte e arriva su un lato qualsiasi (map/anchors.js sceglie quali): esce dritto dal lato per un tratto
 * fisso (stub), poi cerca la strada, ed entra dritto nel lato di arrivo.
 *
 * Griglia "sparsa": le linee possibili sono i bordi dei device (allargati di MARGIN), le metà degli spazi tra
 * un bordo e l'altro, e le righe/colonne di partenza e arrivo. Sulla griglia cerco con A* il percorso più corto,
 * dove ogni curva costa come BEND pixel: escono linee pulite con poche curve.
 * Il tratto orizzontale preferito sta appena sopra il device di arrivo (preferY): così i cavi verso la stessa
 * fila si sovrappongono e formano un'unica linea, come in uno schema di rete fatto a mano.
 *
 * Con centinaia di cavi la mappa ricalcola tutti i percorsi a ogni spostamento: i risultati restano in memoria
 * (stessi capi e stessi ostacoli vicini = stesso percorso) e gli array della ricerca si riusano invece di
 * allocarli e azzerarli ogni volta.
 */
export const MARGIN = 14 // distanza minima tra un cavo e un device
export const STUB = 20 // tratto dritto fisso in uscita e in entrata (più corto se i device sono vicini)
const BEND = 40
const OFF_PREFERRED = 0.02 // piccolo sovrapprezzo per i tratti orizzontali fuori dalla riga preferita
const MAX_CELLS = 60000 // oltre: niente ricerca (meglio un cavo semplice che una mappa lenta)
const NEAR = 400 // considero solo i device vicini al rettangolo tra partenza e arrivo
const CACHE_SIZE = 5000 // percorsi ricordati (i più vecchi escono per primi)

// Direzioni: 0 destra, 1 giù, 2 sinistra, 3 su
const OUT_DIR = { right: 0, bottom: 1, left: 2, top: 3 }
const DX = [1, 0, -1, 0]
const DY = [0, 1, 0, -1]

const half = (v) => Math.round(v * 2) / 2

function uniqueSorted(values) {
  return [...new Set(values.map(half))].sort((a, b) => a - b)
}

/** Aggiunge le metà tra coordinate vicine: i cavi passano in mezzo agli spazi, non rasenti ai device. */
function withMidpoints(values) {
  const out = [...values]
  for (let i = 1; i < values.length; i++) if (values[i] - values[i - 1] > 4) out.push((values[i] + values[i - 1]) / 2)
  return uniqueSorted(out)
}

function lowerIndex(arr, value) {
  let lo = 0
  let hi = arr.length
  while (lo < hi) {
    const mid = (lo + hi) >> 1
    if (arr[mid] < value) lo = mid + 1
    else hi = mid
  }
  return lo
}

/** Coda con priorità minima (heap binario) di indici, con costo separato. */
class Heap {
  constructor() {
    this.items = []
    this.costs = []
  }
  push(item, cost) {
    const { items, costs } = this
    let i = items.length
    items.push(item)
    costs.push(cost)
    while (i > 0) {
      const p = (i - 1) >> 1
      if (costs[p] <= costs[i]) break
      ;[items[p], items[i]] = [items[i], items[p]]
      ;[costs[p], costs[i]] = [costs[i], costs[p]]
      i = p
    }
  }
  pop() {
    const { items, costs } = this
    const top = items[0]
    const lastItem = items.pop()
    const lastCost = costs.pop()
    if (items.length > 0) {
      items[0] = lastItem
      costs[0] = lastCost
      let i = 0
      for (;;) {
        const l = 2 * i + 1
        const r = l + 1
        let m = i
        if (l < items.length && costs[l] < costs[m]) m = l
        if (r < items.length && costs[r] < costs[m]) m = r
        if (m === i) break
        ;[items[m], items[i]] = [items[i], items[m]]
        ;[costs[m], costs[i]] = [costs[i], costs[m]]
        i = m
      }
    }
    return top
  }
  get size() {
    return this.items.length
  }
}

// Array della ricerca riusati: uno stato vale solo se il suo "timbro" è quello della ricerca in corso
let capacity = 0
let costs = new Float64Array(0)
let prevs = new Int32Array(0)
let stamps = new Uint32Array(0)
let blocks = new Uint8Array(0)
let generation = 0

function prepare(cells) {
  const states = cells * 4
  if (states > capacity) {
    capacity = Math.max(states, capacity * 2)
    costs = new Float64Array(capacity)
    prevs = new Int32Array(capacity)
    stamps = new Uint32Array(capacity)
    blocks = new Uint8Array(capacity / 2)
    generation = 0
  }
  generation += 1
  if (generation === 0xffffffff) {
    stamps.fill(0)
    generation = 1
  }
  blocks.fill(0, 0, cells * 2)
}

const cache = new Map()

/**
 * from/to: { x, y, side } punti di attacco sui bordi. rects: [{ x, y, width, height, margin? }] degli ostacoli.
 * preferY: riga preferita per i tratti orizzontali; stub (o stubFrom/stubTo): lunghezza dei tratti dritti alle
 * estremità.
 * Restituisce i punti del percorso (angoli compresi) o null.
 */
export function routeOrthogonal(rawFrom, rawTo, rects, options = {}) {
  // Senza strada con i margini normali (device molto vicini) riprovo con margini stretti: meglio rasente che sotto
  return search(rawFrom, rawTo, rects, options)
    ?? search(rawFrom, rawTo, rects.map((r) => ({ ...r, margin: Math.min(r.margin ?? MARGIN, 3) })), options)
}

function search(rawFrom, rawTo, rects, { preferY: rawPreferY, stub = STUB, stubFrom = stub, stubTo = stub } = {}) {
  // Tutto a mezzo pixel: le coordinate dei bordi devono coincidere con le linee della griglia
  const from = { x: half(rawFrom.x), y: half(rawFrom.y) }
  const to = { x: half(rawTo.x), y: half(rawTo.y) }
  const preferY = Number.isFinite(rawPreferY) ? half(rawPreferY) : null
  const startDir = OUT_DIR[rawFrom.side] ?? 1
  const arriveDir = ((OUT_DIR[rawTo.side] ?? 3) + 2) & 3 // si entra nel lato andando verso l'interno
  // Anche fine e inizio dei tratti dritti a mezzo pixel (i tratti lunghi quanto il nome della porta non lo sono):
  // devono stare esattamente su una linea della griglia, se no la ricerca partirebbe da un'altra cella
  const start = { x: half(from.x + DX[startDir] * stubFrom), y: half(from.y + DY[startDir] * stubFrom) }
  const end = { x: half(to.x - DX[arriveDir] * stubTo), y: half(to.y - DY[arriveDir] * stubTo) }
  const minX = Math.min(start.x, end.x) - NEAR
  const maxX = Math.max(start.x, end.x) + NEAR
  const minY = Math.min(start.y, end.y) - NEAR
  const maxY = Math.max(start.y, end.y) + NEAR
  const box = (r, m) => ({ l: half(r.x - m), r: half(r.x + r.width + m), t: half(r.y - m), b: half(r.y + r.height + m) })
  const boxes = rects
    .map((r) => {
      const wide = box(r, r.margin ?? MARGIN)
      if (!inside(wide, start) && !inside(wide, end)) return wide
      // Partenza o arrivo nel margine di un device vicino: il cavo gli passa rasente, ma mai sotto.
      // Solo se il punto è proprio dentro il device (device sovrapposti) quel device non conta.
      const tight = box(r, 0)
      return inside(tight, start) || inside(tight, end) ? null : tight
    })
    .filter((b) => b && b.r > minX && b.l < maxX && b.b > minY && b.t < maxY)

  const key = `${from.x},${from.y},${startDir},${to.x},${to.y},${arriveDir},${start.x},${start.y},${end.x},${end.y},${preferY}|${
    boxes.map((b) => `${b.l},${b.t},${b.r},${b.b}`).join(';')}`
  if (cache.has(key)) return cache.get(key)
  const points = searchGrid(from, to, start, end, startDir, arriveDir, preferY, boxes)
  cache.set(key, points)
  if (cache.size > CACHE_SIZE) cache.delete(cache.keys().next().value)
  return points
}

function searchGrid(from, to, start, end, startDir, arriveDir, preferY, boxes) {
  const xs = withMidpoints(uniqueSorted([start.x, end.x, ...boxes.flatMap((b) => [b.l, b.r])]))
  const ys = withMidpoints(uniqueSorted([start.y, end.y, ...(preferY === null ? [] : [preferY]), ...boxes.flatMap((b) => [b.t, b.b])]))
  const nx = xs.length
  const ny = ys.length
  if (nx * ny > MAX_CELLS) return null
  const cells = nx * ny
  prepare(cells)

  // Tratti bloccati: blocks[j*nx+i] = tratto da (i,j) a (i+1,j), blocks[cells + j*nx+i] = da (i,j) a (i,j+1)
  for (const b of boxes) {
    const i0 = lowerIndex(xs, b.l)
    const i1 = lowerIndex(xs, b.r)
    const j0 = lowerIndex(ys, b.t)
    const j1 = lowerIndex(ys, b.b)
    // Orizzontali strettamente dentro (t < y < b), tra l e r
    for (let j = j0; j < ny && ys[j] < b.b; j++) {
      if (ys[j] <= b.t) continue
      for (let i = i0; i < i1; i++) blocks[j * nx + i] = 1
    }
    for (let i = i0; i < nx && xs[i] < b.r; i++) {
      if (xs[i] <= b.l) continue
      for (let j = j0; j < j1; j++) blocks[cells + j * nx + i] = 1
    }
  }

  const si = lowerIndex(xs, start.x)
  const sj = lowerIndex(ys, start.y)
  const ei = lowerIndex(xs, end.x)
  const ej = lowerIndex(ys, end.y)
  const goal = ej * nx + ei

  // Stato = cella * 4 + direzione di arrivo
  const heap = new Heap()
  const h = (i, j) => Math.abs(xs[i] - end.x) + Math.abs(ys[j] - end.y)
  const first = (sj * nx + si) * 4 + startDir
  stamps[first] = generation
  costs[first] = 0
  prevs[first] = -1
  heap.push(first, h(si, sj))

  let found = -1
  while (heap.size) {
    const state = heap.pop()
    const cell = state >> 2
    const dir = state & 3
    const c = costs[state]
    if (cell === goal) {
      found = state
      break
    }
    const i = cell % nx
    const j = (cell / nx) | 0
    for (let d = 0; d < 4; d++) {
      if (d === ((dir + 2) & 3)) continue // niente inversioni
      const ni = i + DX[d]
      const nj = j + DY[d]
      if (ni < 0 || nj < 0 || ni >= nx || nj >= ny) continue
      if (d === 0 && blocks[j * nx + i]) continue
      if (d === 2 && blocks[j * nx + ni]) continue
      if (d === 1 && blocks[cells + j * nx + i]) continue
      if (d === 3 && blocks[cells + nj * nx + i]) continue
      const horizontal = d === 0 || d === 2
      const length = horizontal ? Math.abs(xs[ni] - xs[i]) : Math.abs(ys[nj] - ys[j])
      let step = length + (d !== dir ? BEND : 0)
      if (horizontal && preferY !== null && ys[j] !== preferY) step += length * OFF_PREFERRED
      const next = (nj * nx + ni) * 4 + d
      // Arrivo: l'ultimo tratto deve già andare verso il device
      const arrival = nj * nx + ni === goal && d !== arriveDir ? BEND : 0
      const nc = c + step + arrival
      if (stamps[next] !== generation || nc < costs[next]) {
        stamps[next] = generation
        costs[next] = nc
        prevs[next] = state
        heap.push(next, nc + h(ni, nj))
      }
    }
  }
  if (found < 0) return null

  const points = []
  for (let s = found; s >= 0; s = prevs[s]) {
    const cell = s >> 2
    points.push({ x: xs[cell % nx], y: ys[(cell / nx) | 0] })
  }
  points.reverse()
  return simplify([from, ...points, to])
}

function inside(b, p) {
  return p.x > b.l && p.x < b.r && p.y > b.t && p.y < b.b
}

/** Toglie i punti in mezzo a un tratto dritto. */
function simplify(points) {
  const out = []
  for (const p of points) {
    if (out.length && out[out.length - 1].x === p.x && out[out.length - 1].y === p.y) continue
    if (out.length >= 2) {
      const a = out[out.length - 2]
      const b = out[out.length - 1]
      if ((a.x === b.x && b.x === p.x) || (a.y === b.y && b.y === p.y)) out.pop()
    }
    out.push(p)
  }
  return out
}

/** Percorso SVG con angoli arrotondati. */
export function roundedPath(points, radius = 8) {
  if (points.length < 2) return ''
  let d = `M ${points[0].x} ${points[0].y}`
  for (let k = 1; k < points.length - 1; k++) {
    const a = points[k - 1]
    const b = points[k]
    const c = points[k + 1]
    const r = Math.min(radius, Math.hypot(b.x - a.x, b.y - a.y) / 2, Math.hypot(c.x - b.x, c.y - b.y) / 2)
    const inX = b.x - Math.sign(b.x - a.x) * r
    const inY = b.y - Math.sign(b.y - a.y) * r
    const outX = b.x + Math.sign(c.x - b.x) * r
    const outY = b.y + Math.sign(c.y - b.y) * r
    d += ` L ${inX} ${inY} Q ${b.x} ${b.y} ${outX} ${outY}`
  }
  const last = points[points.length - 1]
  return `${d} L ${last.x} ${last.y}`
}
