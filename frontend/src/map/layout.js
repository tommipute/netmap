export const X_GAP = 240
export const Y_GAP = 170
const NODE_H = 64 // altezza tipica di un device in mappa (la posizione si calcola prima di misurarli)
const STACK_GAP = 48 // tra due device impilati nello stesso rack
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

const levelOf = (n) => (Number.isFinite(n.level) ? n.level : 2)
const byName = (a, b) => (a.name || '').localeCompare(b.name || '', 'it', { numeric: true })

/**
 * Blocchi da disporre: i device dello stesso rack stanno insieme, impilati come nel rack
 * (unità più alta in cima); un device senza rack è un blocco da solo. Il blocco sta nella riga
 * del suo device più in alto nella gerarchia.
 */
function buildBlocks(nodes) {
  const groups = new Map()
  for (const n of nodes) {
    const key = n.rack_id ? `rack-${n.rack_id}` : `device-${n.id}`
    if (!groups.has(key)) groups.set(key, [])
    groups.get(key).push(n)
  }
  return [...groups.values()].map((members) => {
    members.sort((a, b) => (b.rack_position ?? -1) - (a.rack_position ?? -1) || byName(a, b))
    return {
      ids: members.map((m) => String(m.id)),
      name: members[0].rack_name || members[0].name || '',
      level: Math.min(...members.map(levelOf)),
      height: members.length * NODE_H + (members.length - 1) * STACK_GAP,
    }
  })
}

/**
 * Disposizione gerarchica: una riga per livello del ruolo (0 in alto).
 * Dentro una riga i blocchi stanno vicino ai device a cui sono collegati sopra
 * (media delle x dei vicini già posizionati). Righe troppo lunghe vanno a capo.
 * nodes: [{ id, name, level, rack_id, rack_name, rack_position }], edges: [{ source, target }] -> { "id": { x, y } }
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
  const blocks = buildBlocks(nodes)
  const levels = [...new Set(blocks.map((b) => b.level))].sort((a, b) => a - b)

  const positions = {}
  // x dei vicini già posizionati (fuori dal blocco): servono per l'ordine e per i corridoi
  const placedNeighbors = (block) =>
    block.ids.flatMap((id) => neighbors.get(id).filter((nid) => positions[nid] && !block.ids.includes(nid)).map((nid) => positions[nid].x))

  let y = 0
  const place = (chunk, xs) => {
    chunk.forEach((block, j) => {
      block.ids.forEach((id, k) => {
        positions[id] = { x: xs[j], y: y + k * (NODE_H + STACK_GAP) }
      })
    })
    y += Math.max(...chunk.map((b) => b.height)) + Y_GAP - NODE_H
  }

  for (const level of levels) {
    const row = blocks.filter((b) => b.level === level)
    const score = new Map(
      row.map((b) => {
        const xs = placedNeighbors(b)
        return [b, xs.length ? xs.reduce((a, c) => a + c, 0) / xs.length : null]
      }),
    )
    row.sort((a, b) => {
      const sa = score.get(a)
      const sb = score.get(b)
      if (sa !== null && sb !== null && sa !== sb) return sa - sb
      if (sa === null && sb !== null) return 1
      if (sa !== null && sb === null) return -1
      return a.name.localeCompare(b.name, 'it', { numeric: true })
    })
    if (row.length <= MAX_PER_ROW) {
      const width = (row.length - 1) * X_GAP
      place(row, row.map((_, j) => j * X_GAP - width / 2))
      continue
    }
    // Fila che va a capo: i cavi verso le file più in basso scendono in verticale sotto i device sopra,
    // quindi lascio libero un corridoio sotto ognuno di loro
    const trunks = [...new Set(row.flatMap(placedNeighbors))]
    const slots = wrappedSlots(trunks, MAX_PER_ROW)
    for (let i = 0; i < row.length; i += MAX_PER_ROW) {
      const chunk = row.slice(i, i + MAX_PER_ROW)
      // Le file incomplete usano gli slot più vicini al centro
      place(chunk, slots.slice(0, chunk.length).sort((p, q) => p - q))
    }
  }
  return positions
}
