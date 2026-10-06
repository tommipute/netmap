export const X_GAP = 210
export const Y_GAP = 150
const MAX_PER_ROW = 8
const NODE_HALF = 86 // metà della larghezza di un device in mappa (.dnode)
const CORRIDOR = 40 // spazio libero tra un cavo verticale e i device accanto

/** Posizioni x per una fila che va a capo, ordinate dal centro verso l'esterno, lontane dai cavi verticali. */
function wrappedSlots(trunks, count) {
  const center = trunks.length ? trunks.reduce((a, b) => a + b, 0) / trunks.length : 0
  const first = trunks.length ? NODE_HALF + CORRIDOR : X_GAP / 2
  const free = (x) => trunks.every((t) => Math.abs(x - t) >= NODE_HALF + CORRIDOR)
  const slots = []
  for (let k = 0; slots.length < count && k < count * 4; k++) {
    for (const side of [-1, 1]) {
      const x = center + side * (first + k * X_GAP)
      if (free(x) && slots.length < count) slots.push(x)
    }
  }
  return slots
}

/**
 * Disposizione gerarchica: una riga per livello del ruolo (0 in alto).
 * Dentro una riga i device stanno vicino a quelli a cui sono collegati sopra
 * (media delle x dei vicini già posizionati). Righe troppo lunghe vanno a capo.
 * nodes: [{ id, name, level }], edges: [{ source, target }] -> { "id": { x, y } }
 */
export function hierarchicalLayout(nodes, edges) {
  const neighbors = new Map(nodes.map((n) => [String(n.id), []]))
  for (const e of edges) {
    const s = String(e.source)
    const t = String(e.target)
    if (neighbors.has(s) && neighbors.has(t)) {
      neighbors.get(s).push(t)
      neighbors.get(t).push(s)
    }
  }
  const nameOf = new Map(nodes.map((n) => [String(n.id), n.name || '']))
  const levelOf = (n) => (Number.isFinite(n.level) ? n.level : 2)
  const levels = [...new Set(nodes.map(levelOf))].sort((a, b) => a - b)

  const positions = {}
  let y = 0
  for (const level of levels) {
    const row = nodes.filter((n) => levelOf(n) === level).map((n) => String(n.id))
    const score = new Map(
      row.map((id) => {
        const xs = neighbors.get(id).filter((nid) => positions[nid]).map((nid) => positions[nid].x)
        return [id, xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : null]
      }),
    )
    row.sort((a, b) => {
      const sa = score.get(a)
      const sb = score.get(b)
      if (sa !== null && sb !== null && sa !== sb) return sa - sb
      if (sa === null && sb !== null) return 1
      if (sa !== null && sb === null) return -1
      return nameOf.get(a).localeCompare(nameOf.get(b), 'it', { numeric: true })
    })
    if (row.length <= MAX_PER_ROW) {
      const width = (row.length - 1) * X_GAP
      row.forEach((id, j) => {
        positions[id] = { x: j * X_GAP - width / 2, y }
      })
      y += Y_GAP
      continue
    }
    // Fila che va a capo: i cavi verso le file più in basso scendono in verticale sotto i device sopra
    // (vedi BusEdge), quindi lascio libero un corridoio sotto ognuno di loro
    const trunks = [...new Set(row.flatMap((id) => neighbors.get(id).filter((nid) => positions[nid]).map((nid) => positions[nid].x)))]
    const slots = wrappedSlots(trunks, MAX_PER_ROW)
    for (let i = 0; i < row.length; i += MAX_PER_ROW) {
      const chunk = row.slice(i, i + MAX_PER_ROW)
      // Le file incomplete usano gli slot più vicini al centro
      const used = slots.slice(0, chunk.length).sort((p, q) => p - q)
      chunk.forEach((id, j) => {
        positions[id] = { x: used[j], y }
      })
      y += Y_GAP
    }
  }
  return positions
}
