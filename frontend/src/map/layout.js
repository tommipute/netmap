export const X_GAP = 210
export const Y_GAP = 150
const MAX_PER_ROW = 8

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
    for (let i = 0; i < row.length; i += MAX_PER_ROW) {
      const chunk = row.slice(i, i + MAX_PER_ROW)
      const width = (chunk.length - 1) * X_GAP
      chunk.forEach((id, j) => {
        positions[id] = { x: j * X_GAP - width / 2, y }
      })
      y += Y_GAP
    }
  }
  return positions
}
