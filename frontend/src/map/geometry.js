/**
 * Geometria di tutti i cavi di una mappa, calcolata in un punto solo (MapEditor).
 *
 * 1. punti di attacco (anchors.js); con i nomi delle porte ogni cavo ha il suo punto, così ogni porta ha un posto
 * 2. percorso di ogni cavo (routing.js, oppure linea dritta)
 * 3. nomi delle porte sul bordo del device, come negli schemi fatti a mano: il tratto dritto che esce dal device
 *    si allunga quanto il nome e il nome ci sta sopra, in verticale se il cavo esce da sopra o da sotto (così
 *    tante porte stanno una accanto all'altra), in orizzontale se esce di lato. A metà cavo non si scrive niente.
 *    Tra due device troppo vicini e allineati i nomi non ci stanno in fila: si scrivono in orizzontale accanto al cavo.
 * 4. punti di ancoraggio disegnati a mano (data.waypoints): il cavo passa da lì, ad angolo retto (o dritto da un
 *    punto all'altro con i cavi dritti), senza percorso automatico. Per modificarli ogni cavo ha `edit`:
 *    corners = i punti da trascinare (per un cavo automatico gli spigoli del percorso calcolato, così il primo
 *    spostamento non cambia la forma del resto), inserts = dove aggiungere un punto ({ x, y, index }).
 */
import { OUTWARD, assignAnchors, rectOf } from './anchors'
import { MARGIN, STUB, routeOrthogonal } from './routing'

const LABEL_H = 16 // altezza del riquadro del nome (font mono 11 px)
const CHAR_W = 6.6
const LABEL_GAP = 4 // distanza del nome dal bordo del device
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

/** Il punto c sta sul tratto dritto che esce da end (lungo al massimo length)? */
function onStub(end, c, length) {
  const o = OUTWARD[end.side]
  const along = (c.x - end.x) * o.x + (c.y - end.y) * o.y
  const across = Math.abs((c.x - end.x) * o.y - (c.y - end.y) * o.x)
  return across < 0.5 && along >= -0.5 && along <= length + 0.5
}

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
 * Cavo ad angolo che passa dai punti di ancoraggio: esce dritto dal device, poi tra un punto e l'altro fa uno
 * spigolo (prima di traverso rispetto al tratto precedente), entra dritto nel device di arrivo.
 * Restituisce { points, keys } con keys = [fine tratto di uscita, ...punti, inizio tratto di entrata].
 */
function throughCorners(from, to, corners, stubFrom, stubTo) {
  const inner = corners.filter((c) => !onStub(from, c, stubFrom) && !onStub(to, c, stubTo))
  const keys = [out(from, stubFrom), ...inner, out(to, stubTo)]
  const path = [from, keys[0]]
  let vertical = OUTWARD[from.side].y !== 0 // direzione dell'ultimo tratto
  for (let i = 1; i < keys.length; i++) {
    const p = keys[i - 1]
    const q = keys[i]
    if (p.x === q.x || p.y === q.y) {
      vertical = p.x === q.x
    } else {
      // L'ultimo spigolo fa entrare il cavo nel verso del lato di arrivo
      const horizontalFirst = i === keys.length - 1 ? OUTWARD[to.side].y !== 0 : vertical
      path.push(horizontalFirst ? { x: q.x, y: p.y } : { x: p.x, y: q.y })
      vertical = horizontalFirst
    }
    path.push(q)
  }
  path.push(to)
  return { points: tidy(path), keys, inner }
}

/** Dove mettere i "+" per aggiungere un punto: a metà di ogni tratto tra due chiavi (sullo spigolo se non sono allineate). */
function insertHandles(keys, orthogonal) {
  const handles = []
  for (let i = 0; i < keys.length - 1; i++) {
    const p = keys[i]
    const q = keys[i + 1]
    const aligned = !orthogonal || p.x === q.x || p.y === q.y
    if (aligned && Math.hypot(q.x - p.x, q.y - p.y) < 24) continue // tratto troppo corto: niente "+"
    handles.push({ ...(aligned ? { x: (p.x + q.x) / 2, y: (p.y + q.y) / 2 } : { x: q.x, y: p.y }), index: i })
  }
  return handles
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
 * mode: 'bus' (ad angolo) o 'straight'.
 * Restituisce { [edgeId]: { points, labels: [{ x, y, text, vertical }] } }.
 */
export function cableGeometry(nodes, bubbles, edges, mode) {
  const withLabels = edges.some((e) => e.data?.sourceLabel)
  const anchors = assignAnchors(nodes, edges, { separate: withLabels })
  const devices = nodes.map((n) => ({ id: n.id, r: rectOf(n) })).filter((d) => d.r)
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
      // Nomi ancora lungo il cavo se i due capi non sono allineati (non si toccano); allineati: accanto al cavo
      const vertical = OUTWARD[from.side].y !== 0
      tight = Boolean(sourceText) && Math.abs(vertical ? from.x - to.x : from.y - to.y) < LABEL_H + 2
      const k = Math.max(0, gap - 4) / (stubFrom + stubTo)
      stubFrom = Math.max(3, stubFrom * k)
      stubTo = Math.max(3, stubTo * k)
    }

    let points
    let edit
    const waypoints = e.data?.waypoints
    if (waypoints?.length && mode === 'bus') {
      const through = throughCorners(from, to, waypoints, stubFrom, stubTo)
      points = through.points
      edit = { corners: through.inner, inserts: insertHandles(through.keys, true) }
    } else if (waypoints?.length) {
      points = [{ x: from.x, y: from.y }, ...waypoints, { x: to.x, y: to.y }]
      edit = { corners: waypoints, inserts: insertHandles(points, false) }
    } else if (mode === 'bus') {
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
      points = routeOrthogonal(from, to, obstacles, { preferY, stubFrom, stubTo }) || fallback(from, to, stubFrom, stubTo)
      // Gli spigoli del percorso automatico diventano i punti da trascinare
      const through = throughCorners(from, to, points.slice(1, -1), stubFrom, stubTo)
      edit = { corners: through.inner, inserts: insertHandles(through.keys, true) }
    } else {
      points = [{ x: from.x, y: from.y }, { x: to.x, y: to.y }]
      edit = { corners: [], inserts: insertHandles(points, false) }
    }

    const labels = []
    if (sourceText && targetText) {
      const place = tight ? besideLabel : edgeLabel
      labels.push(place(from, sourceText), place(to, targetText))
    }
    result[e.id] = { points, labels, edit }
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
