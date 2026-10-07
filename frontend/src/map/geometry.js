/**
 * Geometria di tutti i cavi di una mappa, calcolata in un punto solo (MapEditor).
 *
 * 1. punti di attacco (anchors.js); con i nomi delle porte ogni cavo ha il suo punto, così ogni porta ha un posto
 * 2. percorso ad angolo di ogni cavo (routing.js)
 * 3. nomi delle porte sul bordo del device, come negli schemi fatti a mano: il tratto dritto che esce dal device
 *    si allunga quanto il nome e il nome ci sta sopra, in verticale se il cavo esce da sopra o da sotto (così
 *    tante porte stanno una accanto all'altra), in orizzontale se esce di lato. A metà cavo non si scrive niente.
 *    Tra due device troppo vicini e allineati i nomi non ci stanno in fila: si scrivono in orizzontale accanto al cavo.
 * 4. percorso sistemato a mano (data.waypoints = spigoli): il cavo passa da lì
 *    (connect), senza percorso automatico. Per modificarlo ogni cavo ha `edit` (editInfo): tratti da spostare di
 *    traverso (moveSegment) ed estremità da spostare sul bordo del device (endOnRect). Su un cavo automatico i
 *    tratti sono quelli del percorso calcolato: spostandone uno il resto non cambia.
 */
import { OUTWARD, assignAnchors, rectOf } from './anchors'
import { MARGIN, STUB, routeOrthogonal } from './routing'

const LABEL_H = 16 // altezza del riquadro del nome (font mono 11 px)
const CHAR_W = 6.6
export const PLUG = 7 // sporgenza del connettore disegnato dove il cavo entra nel device
const LABEL_GAP = PLUG + 3 // distanza del nome dal bordo del device: dopo il connettore
const AFTER_LABEL = 10 // tratto dritto dopo il nome, prima della prima curva
const BUS_GAP = 14 // la riga orizzontale preferita sta questo oltre il tratto dritto del device di arrivo

export const labelLength = (text) => String(text).length * CHAR_W + 10

/** Distanza tra due lati che si guardano (null se non si guardano). */
function facingGap(from, to) {
  const out = OUTWARD[from.side]
  if (out.x !== -OUTWARD[to.side].x || out.y !== -OUTWARD[to.side].y) return null
  const gap = out.x ? (to.x - from.x) * out.x : (to.y - from.y) * out.y
  return gap > 0 ? gap : null
}

/** Percorso di riserva se la ricerca non trova strada: esce, una curva a metà, entra. */
function fallback(from, to, stubFrom, stubTo) {
  const a = { x: from.x + OUTWARD[from.side].x * stubFrom, y: from.y + OUTWARD[from.side].y * stubFrom }
  const b = { x: to.x + OUTWARD[to.side].x * stubTo, y: to.y + OUTWARD[to.side].y * stubTo }
  const mid = OUTWARD[from.side].y !== 0
    ? [{ x: a.x, y: (a.y + b.y) / 2 }, { x: b.x, y: (a.y + b.y) / 2 }]
    : [{ x: (a.x + b.x) / 2, y: a.y }, { x: (a.x + b.x) / 2, y: b.y }]
  return [from, a, ...mid, b, to]
}

const out = (end, length) => ({ x: end.x + OUTWARD[end.side].x * length, y: end.y + OUTWARD[end.side].y * length })

/** Toglie punti doppi e punti in mezzo a un tratto dritto. */
function tidy(points) {
  const result = []
  for (const p of points) {
    const last = result[result.length - 1]
    if (last && Math.abs(last.x - p.x) < 0.01 && Math.abs(last.y - p.y) < 0.01) continue
    const prev = result[result.length - 2]
    if (prev && last && ((prev.x === last.x && last.x === p.x) || (prev.y === last.y && last.y === p.y))) result.pop()
    result.push(p)
  }
  return result
}

/**
 * Percorso sistemato a mano: passa dagli spigoli salvati. Il primo spigolo si rimette sulla linea che esce dal
 * device (e l'ultimo su quella che entra), così spostando un device il cavo resta ad angolo retto. Se lo spigolo
 * sta dietro il lato di uscita (estremità spostata su un altro lato) il cavo prima esce dritto di min e poi gira
 * attorno al device. Dove due punti non sono allineati aggiungo uno spigolo.
 */
function connect(from, corners, to, minFrom, minTo) {
  const pts = corners.map((c) => ({ x: c.x, y: c.y }))
  const ahead = (end, c, min) => {
    const o = OUTWARD[end.side]
    return (c.x - end.x) * o.x + (c.y - end.y) * o.y >= min
  }
  const onLine = (end, c) => {
    if (OUTWARD[end.side].y !== 0) c.x = end.x
    else c.y = end.y
  }
  if (pts.length) {
    if (ahead(from, pts[0], minFrom)) onLine(from, pts[0])
    else pts.unshift(out(from, minFrom))
    if (ahead(to, pts[pts.length - 1], minTo)) onLine(to, pts[pts.length - 1])
    else pts.push(out(to, minTo))
  }
  const raw = [{ x: from.x, y: from.y }, ...pts, { x: to.x, y: to.y }]
  const path = [raw[0]]
  let vertical = OUTWARD[from.side].y === 0 // come se prima ci fosse un tratto di traverso: si esce dritti
  for (let k = 1; k < raw.length; k++) {
    const p = path[path.length - 1]
    const q = raw[k]
    if (p.x !== q.x && p.y !== q.y) {
      // L'ultimo spigolo fa entrare il cavo nel verso del lato di arrivo
      const horizontalFirst = k === raw.length - 1 ? OUTWARD[to.side].y !== 0 : vertical
      path.push(horizontalFirst ? { x: q.x, y: p.y } : { x: p.x, y: q.y })
      vertical = horizontalFirst
    } else {
      vertical = p.x === q.x
    }
    path.push(q)
  }
  return tidy(path)
}

/**
 * Cosa si può modificare di un cavo: i tratti interni (non quelli attaccati ai device) si spostano di traverso,
 * le estremità si spostano lungo il bordo del device. segments: [{ index, axis, x, y }] con axis = la coordinata
 * che cambia trascinando (y per un tratto orizzontale).
 */
function editInfo(points, from, to, minFrom, minTo, rects, e) {
  const segments = []
  for (let i = 1; i < points.length - 2; i++) {
    const p = points[i]
    const q = points[i + 1]
    if (Math.hypot(q.x - p.x, q.y - p.y) < 12) continue // troppo corto per prenderlo
    segments.push({ index: i, axis: p.y === q.y ? 'y' : 'x', x: (p.x + q.x) / 2, y: (p.y + q.y) / 2 })
  }
  return {
    points, from, to, minFrom, minTo, segments,
    ends: [
      { end: 'source', x: from.x, y: from.y, rect: rects.get(e.source) },
      { end: 'target', x: to.x, y: to.y, rect: rects.get(e.target) },
    ],
  }
}

/** Spigoli del cavo dopo aver spostato il tratto index alla coordinata value (i tratti ai device restano lunghi almeno il minimo). */
export function moveSegment(edit, index, value) {
  const { points, from, to } = edit
  const axis = edit.segments.find((s) => s.index === index).axis
  let v = value
  const keepOut = (end, min) => {
    const o = OUTWARD[end.side][axis]
    if (o && (v - end[axis]) * o < min) v = end[axis] + o * min
  }
  if (index === 1) keepOut(from, edit.minFrom)
  if (index + 1 === points.length - 2) keepOut(to, edit.minTo)
  const next = points.map((p) => ({ x: p.x, y: p.y }))
  next[index][axis] = v
  next[index + 1][axis] = v
  return next.slice(1, -1)
}

/** Estremità del cavo nel punto del bordo di r più vicino a p: { side, f }. */
export function endOnRect(r, p) {
  const distance = {
    top: Math.abs(p.y - r.y), bottom: Math.abs(p.y - (r.y + r.h)), left: Math.abs(p.x - r.x), right: Math.abs(p.x - (r.x + r.w)),
  }
  const side = Object.keys(distance).reduce((a, b) => (distance[b] < distance[a] ? b : a))
  const raw = side === 'top' || side === 'bottom' ? (p.x - r.x) / r.w : (p.y - r.y) / r.h
  return { side, f: Math.round(Math.min(0.95, Math.max(0.05, raw)) * 100) / 100 }
}

/** Nome della porta lungo il tratto dritto che esce dal device (in verticale se esce da sopra/sotto). */
function edgeLabel(end, text) {
  const out = OUTWARD[end.side]
  const along = LABEL_GAP + labelLength(text) / 2
  return { x: end.x + out.x * along, y: end.y + out.y * along, text, vertical: out.y !== 0 }
}

/** Device vicini: il nome in orizzontale accanto al cavo, appena fuori dal bordo del device. */
function besideLabel(end, text) {
  const out = OUTWARD[end.side]
  if (out.y !== 0) {
    return { x: end.x + labelLength(text) / 2 + 4, y: end.y + out.y * (LABEL_H / 2 + 2), text, vertical: false }
  }
  return { x: end.x + out.x * (labelLength(text) / 2 + 2), y: end.y - LABEL_H / 2 - 3, text, vertical: false }
}

/**
 * nodes: device (nodi React Flow misurati), bubbles: bolle dei rack, edges: cavi React Flow con
 * data.type, data.sourceLabel, data.targetLabel (nomi delle porte, solo se vanno mostrati).
 * Restituisce { [edgeId]: { points, labels: [{ x, y, text, vertical }], edit, ends: [partenza, arrivo] } }.
 */
export function cableGeometry(nodes, bubbles, edges) {
  const withLabels = edges.some((e) => e.data?.sourceLabel)
  const anchors = assignAnchors(nodes, edges, { separate: withLabels })
  const devices = nodes.map((n) => ({ id: n.id, r: rectOf(n) })).filter((d) => d.r)
  const rects = new Map(devices.map((d) => [d.id, d.r]))
  const result = {}

  for (const e of edges) {
    const anchor = anchors[e.id]
    if (!anchor) continue
    const from = anchor.source
    const to = anchor.target
    const sourceText = e.data?.sourceLabel
    const targetText = e.data?.targetLabel
    // Tratti dritti: lunghi quanto il nome (o quelli di sempre senza nomi)
    let stubFrom = sourceText ? LABEL_GAP + labelLength(sourceText) + AFTER_LABEL : STUB
    let stubTo = targetText ? LABEL_GAP + labelLength(targetText) + AFTER_LABEL : STUB
    // Lati che si guardano da vicino: i tratti si accorciano (niente anelli) e i nomi vanno accanto al cavo
    const gap = facingGap(from, to)
    let tight = false
    if (gap !== null && gap < stubFrom + stubTo + 4) {
      // Nomi ancora lungo il cavo se i due capi non sono allineati (non si toccano) o se i due nomi ci stanno in
      // fila nello spazio tra i device; altrimenti accanto al cavo
      const vertical = OUTWARD[from.side].y !== 0
      const span = (text) => (text ? LABEL_GAP + labelLength(text) : 0)
      tight = Boolean(sourceText) && Math.abs(vertical ? from.x - to.x : from.y - to.y) < LABEL_H + 2 &&
        gap < span(sourceText) + span(targetText) + 2
      const k = Math.max(0, gap - 4) / (stubFrom + stubTo)
      stubFrom = Math.max(3, stubFrom * k)
      stubTo = Math.max(3, stubTo * k)
    }

    // Tratto minimo attaccato al device: ci deve stare il nome della porta
    const minOf = (text) => (text ? LABEL_GAP + labelLength(text) + 4 : 12)
    let points
    const waypoints = e.data?.waypoints
    if (waypoints?.length) {
      points = connect(from, waypoints, to, minOf(sourceText), minOf(targetText))
    } else {
      const obstacles = [
        ...devices.map((d) => ({
          x: d.r.x, y: d.r.y, width: d.r.w, height: d.r.h,
          margin: d.id === e.source ? Math.min(MARGIN, stubFrom - 1)
            : d.id === e.target ? Math.min(MARGIN, stubTo - 1) : MARGIN,
        })),
        // Bolle dei rack in cui il cavo non deve entrare: quelle senza la partenza né l'arrivo
        ...bubbles
          .filter((b) => !b.data.ids.includes(e.source) && !b.data.ids.includes(e.target))
          .map((b) => ({ x: b.position.x, y: b.position.y, width: b.width, height: b.height })),
      ]
      const beyond = stubTo + BUS_GAP
      const preferY = to.side === 'top' ? to.y - beyond : to.side === 'bottom' ? to.y + beyond : undefined
      points = tidy(routeOrthogonal(from, to, obstacles, { preferY, stubFrom, stubTo }) || fallback(from, to, stubFrom, stubTo))
    }
    const edit = editInfo(points, from, to, minOf(sourceText), minOf(targetText), rects, e)

    const labels = []
    if (sourceText && targetText) {
      const place = tight ? besideLabel : edgeLabel
      labels.push(place(from, sourceText), place(to, targetText))
    }
    result[e.id] = { points, labels, edit, ends: [from, to] }
  }
  return result
}

const BASE_WIDTH = 172 // larghezza normale di un device (.dnode)
const SLOT = LABEL_H + 6 // spazio per un nome verticale, con un po' di aria tra uno e l'altro

/**
 * Larghezza che serve a ogni device perché i nomi verticali delle porte (cavi che escono da sopra o da sotto)
 * non si tocchino: { nodeId: larghezza } solo per quelli più larghi del normale. Senza nomi nessuno.
 */
export function nodeWidths(nodes, edges) {
  if (!edges.some((e) => e.data?.sourceLabel)) return {}
  const anchors = assignAnchors(nodes, edges, { separate: true })
  const counts = {}
  for (const e of edges) {
    const anchor = anchors[e.id]
    if (!anchor) continue
    for (const [nodeId, end] of [[e.source, anchor.source], [e.target, anchor.target]]) {
      if (end.side !== 'top' && end.side !== 'bottom') continue
      const key = `${nodeId}|${end.side}`
      counts[key] = (counts[key] || 0) + 1
    }
  }
  const widths = {}
  for (const [key, n] of Object.entries(counts)) {
    const nodeId = key.split('|')[0]
    const width = (n + 1) * SLOT
    if (width > BASE_WIDTH && width > (widths[nodeId] || 0)) widths[nodeId] = Math.ceil(width)
  }
  return widths
}
