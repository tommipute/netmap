export const X_GAP = 240
export const Y_GAP = 170
const Y_GAP_WITH_PORTS = 260 // con i nomi delle porte sui cavi serve più spazio tra le righe
const NODE_H = 64 // altezza di riferimento di un device in mappa per lo spazio tra le righe
// Altezza stimata quando il device non è ancora misurato: con l'IP di management c'è una riga in più
const estimatedHeight = (n) => (n.primary_ip ? 76 : 58)
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

/**
 * Livello di ogni device (0 = in alto). Con un ruolo vale il livello del ruolo. Senza ruolo lo ricavo dai
 * collegamenti: un device sta un livello sotto il più vicino device con ruolo; in un gruppo di device tutti
 * senza ruolo, in alto va quello con più collegamenti (di solito il core) e gli altri scendono di un livello per
 * ogni cavo di distanza. Un device senza ruolo e senza cavi va al livello degli switch (2).
 * nodes: [{ id, name, role, level }], edges: [{ source, target }] -> { "id": livello }
 */
export function effectiveLevels(nodes, edges) {
  const ids = nodes.map((n) => String(n.id))
  const neighbors = new Map(ids.map((id) => [id, []]))
  for (const e of edges) {
    const s = String(e.source)
    const t = String(e.target)
    if (neighbors.has(s) && neighbors.has(t) && s !== t) {
      neighbors.get(s).push(t)
      neighbors.get(t).push(s)
    }
  }
  const level = {}
  for (const n of nodes) if (n.role && Number.isFinite(n.level)) level[String(n.id)] = n.level

  // Dai device con ruolo verso quelli senza: livello del ruolo + distanza (il più piccolo vince)
  const spread = (start) => {
    const queue = [...start]
    while (queue.length) {
      const id = queue.shift()
      for (const next of neighbors.get(id)) {
        const fixed = nodes.find((n) => String(n.id) === next)?.role
        if (fixed) continue
        if (level[next] === undefined || level[next] > level[id] + 1) {
          level[next] = level[id] + 1
          queue.push(next)
        }
      }
    }
  }
  spread(Object.keys(level))

  // Gruppi senza nessun ruolo: in alto il device con più collegamenti
  const nameOf = new Map(nodes.map((n) => [String(n.id), n.name || '']))
  for (;;) {
    const free = ids.filter((id) => level[id] === undefined && neighbors.get(id).length > 0)
    if (free.length === 0) break
    free.sort((a, b) => neighbors.get(b).length - neighbors.get(a).length ||
      nameOf.get(a).localeCompare(nameOf.get(b), 'it', { numeric: true }))
    level[free[0]] = 0
    spread([free[0]])
  }
  for (const id of ids) if (level[id] === undefined) level[id] = 2
  return level
}
const byName = (a, b) => (a.name || '').localeCompare(b.name || '', 'it', { numeric: true })

/**
 * Blocchi da disporre: i device dello stesso rack stanno insieme, impilati come nel rack
 * (unità più alta in cima); un device senza rack è un blocco da solo. Il blocco sta nella riga
 * del suo device più in alto nella gerarchia.
 */
function buildBlocks(nodes, heights, levels) {
  const groups = new Map()
  for (const n of nodes) {
    const key = n.rack_id ? `rack-${n.rack_id}` : `device-${n.id}`
    if (!groups.has(key)) groups.set(key, [])
    groups.get(key).push(n)
  }
  return [...groups.values()].map((members) => {
    members.sort((a, b) => (b.rack_position ?? -1) - (a.rack_position ?? -1) || byName(a, b))
    const sizes = members.map((m) => heights[String(m.id)] || estimatedHeight(m))
    // Distanza dall'alto del blocco di ogni device impilato
    const offsets = sizes.map((_, k) => sizes.slice(0, k).reduce((sum, h) => sum + h + STACK_GAP, 0))
    return {
      ids: members.map((m) => String(m.id)),
      offsets,
      name: members[0].rack_name || members[0].name || '',
      level: Math.min(...members.map((m) => levels[String(m.id)])),
      height: offsets[offsets.length - 1] + sizes[sizes.length - 1],
    }
  })
}

/**
 * Disposizione gerarchica: una riga per livello (0 in alto, vedi effectiveLevels).
 * Dentro una riga i blocchi stanno vicino ai device a cui sono collegati sopra
 * (media delle x dei vicini già posizionati). Righe troppo lunghe vanno a capo.
 * nodes: [{ id, name, level, rack_id, rack_name, rack_position, primary_ip }], edges: [{ source, target }],
 * heights: { id: altezza misurata } se disponibili; withPorts: righe più distanti per i nomi delle porte;
 * widths: { id: larghezza } dei device allargati per i nomi delle porte (stanno centrati sul loro posto e
 * allontanano i vicini nella fila)
 * -> { "id": { x, y } }
 */
export function hierarchicalLayout(nodes, edges, heights = {}, { withPorts = false, widths = {} } = {}) {
  const widthOf = (id) => widths[id] || NODE_HALF * 2
  const blockWidth = (block) => Math.max(...block.ids.map(widthOf))
  const rowGap = (withPorts ? Y_GAP_WITH_PORTS : Y_GAP) - NODE_H
  const neighbors = new Map(nodes.map((n) => [String(n.id), []]))
  for (const e of edges) {
    const s = String(e.source)
    const t = String(e.target)
    if (neighbors.has(s) && neighbors.has(t)) {
      neighbors.get(s).push(t)
      neighbors.get(t).push(s)
    }
  }
  const blocks = buildBlocks(nodes, heights, effectiveLevels(nodes, edges))
  const levels = [...new Set(blocks.map((b) => b.level))].sort((a, b) => a - b)

  const positions = {}
  // x dei vicini già posizionati (fuori dal blocco): servono per l'ordine e per i corridoi
  const placedNeighbors = (block) =>
    block.ids.flatMap((id) => neighbors.get(id).filter((nid) => positions[nid] && !block.ids.includes(nid)).map((nid) => positions[nid].x))

  let y = 0
  const place = (chunk, xs) => {
    chunk.forEach((block, j) => {
      block.ids.forEach((id, k) => {
        positions[id] = { x: xs[j] + NODE_HALF - widthOf(id) / 2, y: y + block.offsets[k] }
      })
    })
    y += Math.max(...chunk.map((b) => b.height)) + rowGap
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
      // Passo normale X_GAP; un device allargato spinge più in là i vicini
      const xs = [0]
      for (let j = 1; j < row.length; j++) {
        const extra = (blockWidth(row[j - 1]) + blockWidth(row[j])) / 2 - NODE_HALF * 2
        xs.push(xs[j - 1] + X_GAP + Math.max(0, extra))
      }
      const width = xs[xs.length - 1]
      place(row, xs.map((x) => x - width / 2))
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

// Bolle delle posizioni: spazio attorno al contenuto (in alto il nome) e tra due bolle vicine
export const LOC_PAD = { top: 44, side: 26, bottom: 24 }
const LOC_GAP = 70
// Spazio attorno ai device per le bolle dei rack (come RACK_PAD in MapEditor)
const DEVICE_PAD = { top: 10, side: 16, bottom: 30 }

/** Posizioni sorelle: piano più alto in cima (quota), poi senza quota in ordine di nome. */
const byFloor = (a, b) =>
  (a.floor == null) - (b.floor == null) || (b.floor ?? 0) - (a.floor ?? 0) || byName(a, b)

/**
 * Disposizione per posizione: ogni posizione è un riquadro con dentro i suoi device (disposti per ruolo come in
 * hierarchicalLayout) e le posizioni che contiene. Gli edifici (primo livello) stanno affiancati; dentro un
 * edificio, o se le posizioni hanno una quota, i figli stanno impilati (quota più alta in cima), altrimenti
 * affiancati (es. le stanze di un piano). I device senza posizione stanno in alto, fuori dai riquadri.
 * locations: [{ id, name, parent_id, floor }] (vedi view.locations) -> { "id": { x, y } }
 */
export function locationLayout(nodes, edges, locations, heights = {}, options = {}) {
  const widths = options.widths || {}
  const known = new Map(locations.map((l) => [l.id, l]))
  const keyOf = (id) => (id && known.has(id) ? id : 'root')
  const children = new Map()
  for (const l of locations) {
    const parent = keyOf(l.parent_id)
    if (!children.has(parent)) children.set(parent, [])
    children.get(parent).push(l)
  }
  const direct = new Map()
  for (const n of nodes) {
    const key = keyOf(n.location_id)
    if (!direct.has(key)) direct.set(key, [])
    direct.get(key).push(n)
  }

  // Riquadro: { positions (relative all'angolo in alto a sinistra), w, h }
  const devicesBox = (list) => {
    if (!list.length) return null
    const pos = hierarchicalLayout(list, edges, heights, options)
    let l = Infinity, t = Infinity, r = -Infinity, b = -Infinity
    for (const n of list) {
      const p = pos[String(n.id)]
      const w = widths[String(n.id)] || NODE_HALF * 2
      const h = heights[String(n.id)] || estimatedHeight(n)
      l = Math.min(l, p.x - DEVICE_PAD.side)
      t = Math.min(t, p.y - DEVICE_PAD.top)
      r = Math.max(r, p.x + w + DEVICE_PAD.side)
      b = Math.max(b, p.y + h + DEVICE_PAD.bottom)
    }
    const positions = Object.fromEntries(Object.entries(pos).map(([id, p]) => [id, { x: p.x - l, y: p.y - t }]))
    return { positions, w: r - l, h: b - t }
  }
  const shift = (box, dx, dy, into) => {
    for (const [id, p] of Object.entries(box.positions)) into[id] = { x: p.x + dx, y: p.y + dy }
  }
  // Contenuto di una posizione (o della mappa intera): device propri sopra, poi le posizioni figlie
  const contentBox = (key, depth) => {
    const own = devicesBox(direct.get(key) || [])
    const kids = (children.get(key) || []).slice().sort(byFloor)
      .map((loc) => {
        const inner = contentBox(loc.id, depth + 1)
        if (!inner) return null
        const positions = {}
        shift(inner, LOC_PAD.side, LOC_PAD.top, positions)
        return { positions, w: inner.w + LOC_PAD.side * 2, h: inner.h + LOC_PAD.top + LOC_PAD.bottom }
      })
      .filter(Boolean)
    if (!own && kids.length === 0) return null
    // Edifici affiancati; i piani di un edificio (o figli con quota) impilati; il resto affiancato
    const stacked = depth === 1 || (depth > 1 && (children.get(key) || []).some((l) => l.floor != null))
    // Righe una sotto l'altra, centrate: i device propri, poi i figli (uno per riga se impilati, tutti in una se no)
    const rows = []
    if (own) rows.push([own])
    if (stacked) rows.push(...kids.map((k) => [k]))
    else if (kids.length) rows.push(kids)
    const rowWidth = (row) => row.reduce((sum, k) => sum + k.w, 0) + LOC_GAP * (row.length - 1)
    const w = Math.max(...rows.map(rowWidth))
    const positions = {}
    let y = 0
    for (const row of rows) {
      let x = (w - rowWidth(row)) / 2
      for (const k of row) {
        shift(k, x, y, positions)
        x += k.w + LOC_GAP
      }
      y += Math.max(...row.map((k) => k.h)) + LOC_GAP
    }
    y -= LOC_GAP
    return { positions, w, h: y }
  }
  return contentBox('root', 0)?.positions || {}
}
