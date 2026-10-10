import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import {
  Background,
  BackgroundVariant,
  ConnectionMode,
  Controls,
  MiniMap,
  Panel,
  ReactFlow,
  ReactFlowProvider,
  getNodesBounds,
  useNodesState,
  useReactFlow,
} from '@xyflow/react'
import { toPng, toSvg } from 'html-to-image'
import { api } from '../api'
import { useAuth } from '../auth'
import { useTheme } from '../theme'
import { Badge, LiveStatus } from '../components/Bits'
import CableDialog from '../components/CableDialog'
import { IconButton, IconLink } from '../components/Icon'
import RefLabel from '../components/RefLabel'
import { invalidate } from '../hooks'
import CableEdge from '../map/CableEdge'
import { cableStyle } from '../map/cables'
import { cableGeometry, labelBox, nodeSizes } from '../map/geometry'
import DeviceNode from '../map/DeviceNode'
import MapSearch from '../map/MapSearch'
import { shortPortName } from '../map/ports'
import LocationNode from '../map/LocationNode'
import MapLabels from '../map/MapLabels'
import RackNode from '../map/RackNode'
import { LOC_PAD, X_GAP, Y_GAP, effectiveLevels, hierarchicalLayout, locationLayout } from '../map/layout'
import { CABLE_STATUS, CABLE_TYPES, DEVICE_STATUS, formatSpeed, labelOf } from '../options'
import { t } from '../i18n'

const nodeTypes = { device: DeviceNode, rack: RackNode, location: LocationNode }
const edgeTypes = { cable: CableEdge }
const HINT_MS = 6000 // il suggerimento in alto resta per qualche secondo
const REFRESH_MS = 30000 // stato live: la mappa si aggiorna da sola
const EXPORT_PADDING = 40

function download(dataUrl, filename) {
  const a = document.createElement('a')
  a.href = dataUrl
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
}

// Bolle delle posizioni accese o spente (scelta ricordata nel browser)
const LOCATIONS_PREF = 'netmap.map.locations'
function readLocationsPref() {
  try {
    return localStorage.getItem(LOCATIONS_PREF) !== '0'
  } catch {
    return true
  }
}

const same = (a, b) => JSON.stringify(a) === JSON.stringify(b)

/**
 * Nodi per React Flow: posizione attuale > posizione salvata > calcolata. Un device già in mappa tiene il suo
 * oggetto (con le misure di React Flow): ricreandolo i device restavano un attimo senza misure, cavi e bolle
 * sparivano e la mappa lampeggiava a ogni aggiornamento dello stato live.
 */
function buildFlowNodes(view, previous) {
  const known = new Map(previous.map((n) => [n.id, n]))
  const nodes = view.nodes.map((n) => {
    const id = String(n.id)
    const prev = known.get(id)
    if (prev) return same(prev.data, n) ? prev : { ...prev, data: n }
    const position = n.x !== null && n.y !== null ? { x: n.x, y: n.y } : null
    return { id, type: 'device', position, data: n }
  })
  const missing = nodes.filter((n) => !n.position)
  if (missing.length === 0) return { nodes, changed: false }

  if (missing.length === nodes.length) {
    // Con le posizioni accese i device si raggruppano per edificio/piano/stanza, altrimenti righe per ruolo
    const layout = readLocationsPref() && view.locations.length
      ? locationLayout(view.nodes, view.edges, view.locations)
      : hierarchicalLayout(view.nodes, view.edges)
    return { nodes: nodes.map((n) => ({ ...n, position: layout[n.id] })), changed: true }
  }
  // Device nuovi in una mappa già disposta: li metto in fila sotto
  const placed = nodes.filter((n) => n.position)
  const bottom = Math.max(...placed.map((n) => n.position.y)) + Y_GAP
  const left = Math.min(...placed.map((n) => n.position.x))
  let i = 0
  return {
    nodes: nodes.map((n) => (n.position ? n : { ...n, position: { x: left + X_GAP * i++, y: bottom } })),
    changed: true,
  }
}

// Margini della bolla di un rack attorno ai suoi device. In alto poco spazio, così la linea comune dei cavi
// (28 px sopra i device, vedi map/geometry.js) resta fuori; in basso c'è il nome del rack.
const RACK_PAD = { top: 10, side: 16, bottom: 30 }

const bubbleBox = (members) => ({
  l: Math.min(...members.map((n) => n.position.x)) - RACK_PAD.side,
  t: Math.min(...members.map((n) => n.position.y)) - RACK_PAD.top,
  r: Math.max(...members.map((n) => n.position.x + n.measured.width)) + RACK_PAD.side,
  b: Math.max(...members.map((n) => n.position.y + n.measured.height)) + RACK_PAD.bottom,
})
const overlaps = (box, n) =>
  n.position.x < box.r && n.position.x + n.measured.width > box.l && n.position.y < box.b && n.position.y + n.measured.height > box.t

/**
 * Bolle dei rack: rettangoli sotto i device dello stesso rack, ricalcolati a ogni spostamento.
 * Se tra due device del rack c'è un device di un altro rack, il rack si divide in più bolle (con lo stesso
 * nome) invece di coprirlo: unisco i gruppi più vicini finché la bolla unita non copre nessun estraneo.
 */
/** Un tratto orizzontale o verticale del cavo passa nel riquadro? */
const crosses = (p, q, box) =>
  Math.max(p.x, q.x) >= box.l && Math.min(p.x, q.x) <= box.r && Math.max(p.y, q.y) >= box.t && Math.min(p.y, q.y) <= box.b

const RACK_NAME_H = 20
const boxesHit = (a, b) => a.l < b.r && b.l < a.r && a.t < b.b && b.t < a.b

/**
 * Nome di ogni bolla dei rack: nel primo dei quattro angoli dove non copre niente (in basso a sinistra, in basso a
 * destra, in alto appena fuori dalla bolla a sinistra e a destra), altrimenti dove copre meno (device, nomi delle
 * porte e degli altri rack contano più dei cavi). Sta sopra i cavi (MapLabels): non lo copre niente.
 * -> [{ bubble, text, box: { l, t, r, b } }]
 */
function rackNames(bubbles, geometry, nodes) {
  const devices = nodes.filter((n) => n.measured?.width).map((n) => ({
    l: n.position.x, t: n.position.y, r: n.position.x + n.measured.width, b: n.position.y + n.measured.height,
  }))
  const parts = Object.values(geometry)
  const labels = parts.flatMap((g) => g.labels.map(labelBox))
  const segments = parts.flatMap((g) => g.points.slice(1).map((q, i) => [g.points[i], q]))
  const placed = []
  return bubbles.map((bubble) => {
    const text = `Rack ${bubble.data.name}`
    const width = text.length * 6.6 + 12
    const { x, y } = bubble.position
    const bottom = y + bubble.height - RACK_NAME_H - 4
    const top = y - RACK_NAME_H - 2
    const right = x + bubble.width - 10 - width
    const corners = [[x + 10, bottom], [right, bottom], [x + 10, top], [right, top]]
      .map(([l, t]) => ({ l, t, r: l + width, b: t + RACK_NAME_H }))
    const cost = (c) =>
      10 * (devices.filter((d) => boxesHit(c, d)).length + placed.filter((d) => boxesHit(c, d)).length) +
      3 * labels.filter((d) => boxesHit(c, d)).length +
      segments.filter(([p, q]) => crosses(p, q, c)).length
    let box = corners[0]
    let best = cost(box)
    for (const c of corners.slice(1)) {
      if (best === 0) break
      const k = cost(c)
      if (k < best) {
        box = c
        best = k
      }
    }
    placed.push(box)
    return { bubble, text, box }
  })
}

function rackBubbles(nodes, onSelect) {
  const measured = nodes.filter((n) => n.measured?.width)
  const groups = new Map()
  for (const n of measured) {
    if (!n.data.rack_id) continue
    if (!groups.has(n.data.rack_id)) groups.set(n.data.rack_id, [])
    groups.get(n.data.rack_id).push(n)
  }
  const bubbles = []
  for (const [rackId, members] of groups) {
    // Una bolla unita sta sempre dentro quella di tutto il rack: contano solo gli estranei lì dentro (di solito
    // nessuno, e allora la bolla è una sola). La bolla di due gruppi è l'unione delle loro.
    const whole = bubbleBox(members)
    const others = measured.filter((n) => n.data.rack_id !== rackId && overlaps(whole, n))
    let clusters = others.length ? members.map((n) => ({ members: [n], box: bubbleBox([n]) })) : [{ members, box: whole }]
    while (clusters.length > 1) {
      let best = null
      for (let i = 0; i < clusters.length; i++) {
        for (let j = i + 1; j < clusters.length; j++) {
          const a = clusters[i].box
          const b = clusters[j].box
          const box = { l: Math.min(a.l, b.l), t: Math.min(a.t, b.t), r: Math.max(a.r, b.r), b: Math.max(a.b, b.b) }
          if (others.some((n) => overlaps(box, n))) continue
          const area = (box.r - box.l) * (box.b - box.t)
          if (!best || area < best.area) best = { i, j, box, area }
        }
      }
      if (!best) break
      clusters[best.i] = { members: [...clusters[best.i].members, ...clusters[best.j].members], box: best.box }
      clusters = clusters.filter((_, k) => k !== best.j)
    }
    const allIds = members.map((n) => n.id)
    clusters.forEach(({ members: cluster, box }, k) => {
      bubbles.push({
        id: `rack-${rackId}-${k}`,
        type: 'rack',
        position: { x: box.l, y: box.t },
        width: box.r - box.l,
        height: box.b - box.t,
        data: {
          name: members[0].data.rack_name,
          count: members.length,
          ids: cluster.map((n) => n.id),
          onSelect: () => onSelect(allIds),
        },
        selectable: false,
        draggable: false,
        connectable: false,
        focusable: false,
        zIndex: -1,
      })
    })
  }
  return bubbles
}

/**
 * Bolle delle posizioni: per ogni posizione un riquadro attorno ai suoi device e alle posizioni che contiene
 * (quindi una dentro l'altra: edificio › piano › stanza), ricalcolato a ogni spostamento. extras: { nodeId: [box] }
 * = altro che appartiene al device (nomi delle porte, nome del rack), così il nome della posizione in alto resta libero. Sotto le bolle dei rack;
 * a differenza di quelle i cavi le attraversano.
 */
function locationBubbles(nodes, locations, onSelect, extras = new Map()) {
  if (!locations.length) return []
  const measured = nodes.filter((n) => n.measured?.width)
  const known = new Map(locations.map((l) => [l.id, l]))
  const children = new Map()
  for (const l of locations) {
    if (!known.has(l.parent_id)) continue
    if (!children.has(l.parent_id)) children.set(l.parent_id, [])
    children.get(l.parent_id).push(l)
  }
  const bubbles = []
  const visit = (loc, depth) => {
    const boxes = []
    const ids = []
    for (const n of measured) {
      if (n.data.location_id !== loc.id) continue
      boxes.push(bubbleBox([n]), ...(extras.get(n.id) || []))
      ids.push(n.id)
    }
    for (const child of children.get(loc.id) || []) {
      const inner = visit(child, depth + 1)
      if (inner) {
        boxes.push(inner.box)
        ids.push(...inner.ids)
      }
    }
    if (boxes.length === 0) return null
    const box = {
      l: Math.min(...boxes.map((b) => b.l)) - LOC_PAD.side,
      t: Math.min(...boxes.map((b) => b.t)) - LOC_PAD.top,
      r: Math.max(...boxes.map((b) => b.r)) + LOC_PAD.side,
      b: Math.max(...boxes.map((b) => b.b)) + LOC_PAD.bottom,
    }
    bubbles.push({
      id: `location-${loc.id}`,
      type: 'location',
      position: { x: box.l, y: box.t },
      width: box.r - box.l,
      height: box.b - box.t,
      data: { name: loc.name, path: loc.path, depth, ids, onSelect: () => onSelect(ids) },
      selectable: false,
      draggable: false,
      connectable: false,
      focusable: false,
      zIndex: -10 + depth, // la posizione contenuta sopra quella che la contiene, tutte sotto i rack (-1)
    })
    return { box, ids }
  }
  for (const l of locations) if (!known.has(l.parent_id)) visit(l, 0)
  return bubbles
}

function toFlowEdge(edge, levelOf, showLabels, selected, route) {
  // Il cavo parte sempre dal device più in alto nella gerarchia
  const flip = (levelOf[edge.source] ?? 0) > (levelOf[edge.target] ?? 0)
  // Percorso sistemato a mano: salvato dal lato A al lato B del cavo, in mappa nel verso source -> target
  const waypoints = route?.points?.length ? (flip ? [...route.points].reverse() : route.points) : null
  const style = cableStyle(edge.type)
  const fast = (edge.speed_mbps || 0) >= 10000
  return {
    id: `cable-${edge.id}`,
    source: String(flip ? edge.target : edge.source),
    target: String(flip ? edge.source : edge.target),
    type: 'cable',
    data: {
      ...edge,
      flip,
      waypoints,
      sourceEnd: (flip ? route?.b_end : route?.a_end) || null,
      targetEnd: (flip ? route?.a_end : route?.b_end) || null,
      // Nomi delle porte, ognuno vicino al suo device: corti (Te1/1/1), quello intero passando sopra
      sourceLabel: showLabels ? shortPortName(flip ? edge.target_interface : edge.source_interface) : null,
      targetLabel: showLabels ? shortPortName(flip ? edge.source_interface : edge.target_interface) : null,
      sourceTitle: flip ? edge.target_interface : edge.source_interface,
      targetTitle: flip ? edge.source_interface : edge.target_interface,
    },
    labelBgPadding: [5, 2],
    labelBgBorderRadius: 3,
    className: selected ? 'cable cable--selected' : 'cable',
    style: {
      stroke: style.color,
      strokeWidth: (fast ? 3.5 : 2) + (selected ? 2 : 0),
      strokeDasharray: edge.status === 'planned' ? '7 5' : edge.status === 'decommissioning' ? '2 4' : undefined,
    },
  }
}

/**
 * Legenda in basso. I tipi di cavo sono pulsanti: cliccandone uno la mappa mostra solo i cavi di quel tipo
 * (cableTypes = tipi scelti, vuoto = tutti); se ne possono scegliere più di uno, un secondo clic lo toglie.
 */
function Legend({ edges, nodes, racks, locations, vlan, cableTypes, onCableTypes }) {
  const types = [...new Set(edges.map((e) => e.type || ''))]
  const planned = edges.some((e) => e.status === 'planned')
  const live = nodes.some((n) => n.reachable !== null && n.reachable !== undefined)
  if (types.length === 0 && !live && !racks && !locations && !vlan) return null
  return (
    <div className="map-legend">
      {vlan && <span className="map-legend__item"><span className="map-legend__line map-legend__line--vlan" />VLAN {vlan.vid} {vlan.name}</span>}
      {locations && <span className="map-legend__item"><span className="map-legend__loc" />{t('Posizione')}</span>}
      {racks && <span className="map-legend__item"><span className="map-legend__rack" />{t('Rack')}</span>}
      {live && (
        <>
          <span className="map-legend__item"><span className="live-dot live-dot--up" />{t('Risponde')}</span>
          <span className="map-legend__item"><span className="live-dot live-dot--down" />{t('Non risponde')}</span>
        </>
      )}
      {types.map((type) => {
        const style = cableStyle(type || null)
        const chosen = cableTypes.includes(type)
        const off = cableTypes.length > 0 && !chosen
        return (
          <button key={type || 'none'} type="button" aria-pressed={chosen}
            className={`map-legend__item map-legend__toggle nodrag nopan${off ? ' map-legend__toggle--off' : ''}`}
            title={chosen ? t('Clic per togliere questo tipo dai cavi mostrati') : t('Clic per mostrare solo i cavi di questo tipo')}
            onClick={() => onCableTypes(chosen ? cableTypes.filter((x) => x !== type) : [...cableTypes, type])}>
            <span className="map-legend__line" style={{ background: style.color }} />
            {style.label}
          </button>
        )
      })}
      {cableTypes.length > 0 && (
        <button type="button" className="map-legend__item map-legend__toggle map-legend__all nodrag nopan" onClick={() => onCableTypes([])}>
          {t('Tutti i cavi')}
        </button>
      )}
      {planned && (
        <span className="map-legend__item">
          <span className="map-legend__line map-legend__line--dashed" />
          {t('Pianificato')}
        </span>
      )}
    </div>
  )
}

function Editor() {
  const { id } = useParams()
  const { canEdit } = useAuth()
  const [theme] = useTheme()
  const { fitView, getNodes, getZoom, setCenter } = useReactFlow()
  const [view, setView] = useState(null)
  const [error, setError] = useState(null)
  const [nodes, setNodes, onNodesChange] = useNodesState([])
  const [dirty, setDirty] = useState(false)
  const [saving, setSaving] = useState(false)
  const [showLabels, setShowLabels] = useState(false)
  const [cableTypes, setCableTypes] = useState([]) // tipi di cavo scelti nella legenda, vuoto = tutti
  const [showLocations, setShowLocations] = useState(readLocationsPref)
  const [selection, setSelection] = useState(null) // { kind: 'node' | 'edge', id, found? }
  const [vlanId, setVlanId] = useState(null) // vista VLAN: evidenzia device e cavi che la portano
  // Cavi sistemati a mano: { cableId: { points: spigoli dal lato A al lato B, a_end, b_end: { side, f } | null } }
  const [routes, setRoutes] = useState({})
  const routesRef = useRef(routes)
  routesRef.current = routes
  const [connecting, setConnecting] = useState(null) // { a, b } id device
  const [checking, setChecking] = useState(false)

  const nodesRef = useRef(nodes)
  nodesRef.current = nodes
  const fitRef = useRef(fitView)
  fitRef.current = fitView
  // fitView funziona solo dopo che React Flow ha misurato i device: lo chiedo e lo eseguo appena sono pronti.
  // Non uso useNodesInitialized: le bolle dei rack hanno già le misure e lo farebbero scattare troppo presto.
  const devicesMeasured = nodes.length > 0 && nodes.every((n) => n.measured?.width)
  const fitPending = useRef(false)

  const load = useCallback(
    async (keepPositions) => {
      try {
        const data = await api.get(`/maps/${id}/view`)
        const { nodes: built, changed } = buildFlowNodes(data, keepPositions ? nodesRef.current : [])
        // Ricaricando (stato live ogni 30 s) restano i punti che si stanno modificando
        if (!keepPositions) setRoutes(Object.fromEntries(data.routes.map(({ cable_id: cableId, ...route }) => [cableId, route])))
        // Le parti della vista che non cambiano restano gli stessi oggetti: niente ricalcolo di cavi e bolle
        setView((prev) => (prev && keepPositions
          ? Object.fromEntries(Object.entries(data).map(([key, value]) => [key, same(prev[key], value) ? prev[key] : value]))
          : data))
        setNodes(built)
        setError(null)
        if (changed) setDirty(true)
        return data
      } catch (err) {
        setError(err.message)
        return null
      }
    },
    [id, setNodes],
  )

  useEffect(() => {
    setDirty(false)
    setSelection(null)
    setVlanId(null)
    fitPending.current = true
    load(false)
  }, [load])

  useEffect(() => {
    if (devicesMeasured && fitPending.current) {
      fitPending.current = false
      // Al fotogramma dopo: nel frattempo compaiono le bolle dei rack, calcolate dai device appena misurati
      requestAnimationFrame(() => fitRef.current({ padding: 0.25 }))
    }
  }, [devicesMeasured])

  // Suggerimento su come collegare due device: sparisce da solo dopo qualche secondo (o con la x)
  const [hint, setHint] = useState(true)
  useEffect(() => {
    const timer = setTimeout(() => setHint(false), HINT_MS)
    return () => clearTimeout(timer)
  }, [])

  // Pulsante "Aggiorna": come l'aggiornamento automatico, ma subito (device o cavi aggiunti da un'altra pagina)
  const [reloading, setReloading] = useState(false)
  const reload = useCallback(async () => {
    setReloading(true)
    await load(true)
    setReloading(false)
  }, [load])

  // Stato live: ricarico i dati dei device senza toccare le posizioni
  const connectingRef = useRef(connecting)
  connectingRef.current = connecting
  useEffect(() => {
    const timer = setInterval(() => {
      if (!document.hidden && !connectingRef.current) load(true)
    }, REFRESH_MS)
    return () => clearInterval(timer)
  }, [load])

  // Avviso se si chiude la pagina con modifiche non salvate
  useEffect(() => {
    if (!dirty || !canEdit) return undefined
    const handler = (e) => {
      e.preventDefault()
      e.returnValue = ''
    }
    window.addEventListener('beforeunload', handler)
    return () => window.removeEventListener('beforeunload', handler)
  }, [dirty, canEdit])

  // Livelli anche per i device senza ruolo (ricavati dai collegamenti): il cavo parte dal device più in alto
  const levelOf = useMemo(() => effectiveLevels(view?.nodes || [], view?.edges || []), [view])
  const baseEdges = useMemo(
    () =>
      (view?.edges || [])
        // Filtro della legenda: solo i cavi dei tipi scelti (gli altri non ci sono proprio: più spazio ai nomi)
        .filter((e) => cableTypes.length === 0 || cableTypes.includes(e.type || ''))
        .map((e) => toFlowEdge(e, levelOf, showLabels, selection?.kind === 'edge' && selection.id === e.id, routes[e.id])),
    [view, levelOf, showLabels, selection, routes, cableTypes],
  )

  /**
   * Modifica a mano di un cavo, nel verso della mappa: { points } (spigoli), { sourceEnd } / { targetEnd }
   * (dove si attacca) oppure { reset: true } (tutto automatico).
   */
  const changeRoute = useCallback((cableId, flip, change) => {
    setRoutes((current) => {
      const next = { ...current }
      const route = { points: [], a_end: null, b_end: null, ...current[cableId] }
      if (change.points) route.points = flip ? [...change.points].reverse() : change.points
      if (change.sourceEnd) route[flip ? 'b_end' : 'a_end'] = change.sourceEnd
      if (change.targetEnd) route[flip ? 'a_end' : 'b_end'] = change.targetEnd
      if (change.reset || (!route.points.length && !route.a_end && !route.b_end)) delete next[cableId]
      else next[cableId] = route
      return next
    })
    setDirty(true)
  }, [])

  // Clic sul nome di un rack: seleziono i suoi device, trascinandone uno si spostano tutti
  const selectRack = useCallback(
    (ids) => {
      setSelection(null)
      setNodes((current) => current.map((n) => ({ ...n, selected: ids.includes(n.id) })))
    },
    [setNodes],
  )
  // Gestori stabili: React Flow li passa a ogni device e cavo, una funzione nuova a ogni render li ridisegnerebbe
  // tutti (in una mappa grande, a ogni movimento del mouse mentre si trascina)
  const onNodeDragStop = useCallback(() => setDirty(true), [])
  const onNodeClick = useCallback(
    (_, node) => node.type === 'device' && setSelection({ kind: 'node', id: Number(node.id) }), [])
  const onEdgeClick = useCallback((_, edge) => setSelection({ kind: 'edge', id: edge.data.id }), [])
  const onPaneClick = useCallback(() => setSelection(null), [])
  const onConnect = useCallback(
    ({ source, target }) => source !== target && setConnecting({ a: Number(source), b: Number(target) }), [])
  const bubbles = useMemo(() => rackBubbles(nodes, selectRack), [nodes, selectRack])
  const locationsOn = showLocations && (view?.locations.length || 0) > 0
  // Percorsi ed etichette di tutti i cavi: dipendono dalle posizioni. Mentre si trascina ricalcolo solo i cavi dei
  // device che si muovono (con centinaia di cavi rifarli tutti a ogni movimento del mouse rallenta la mappa); al
  // rilascio si ricalcolano tutti (map/routing.js ricorda i percorsi che non cambiano).
  const moving = useMemo(() => nodes.filter((n) => n.dragging).map((n) => n.id).join(','), [nodes])
  const lastGeometry = useRef({})
  const geometry = useMemo(() => {
    const only = moving ? new Set(moving.split(',')) : null
    const next = cableGeometry(nodes, bubbles, baseEdges, { only, previous: lastGeometry.current })
    lastGeometry.current = next
    return next
  }, [nodes, bubbles, baseEdges, moving])
  const rackLabels = useMemo(() => rackNames(bubbles, geometry, nodes), [bubbles, geometry, nodes])
  const places = useMemo(() => {
    if (!locationsOn) return []
    // Le bolle delle posizioni comprendono anche i nomi delle porte e dei rack dei loro device
    const extras = new Map()
    const add = (nodeId, box) => {
      if (!extras.has(nodeId)) extras.set(nodeId, [])
      extras.get(nodeId).push(box)
    }
    for (const g of Object.values(geometry)) for (const l of g.labels) add(l.node, labelBox(l))
    for (const { bubble, box } of rackLabels) add(bubble.data.ids[0], box)
    return locationBubbles(nodes, view.locations, selectRack, extras)
  }, [locationsOn, nodes, view, selectRack, geometry, rackLabels])
  // Con i nomi delle porte un device con tanti cavi sullo stesso lato si allarga (o si allunga) quanto serve
  const sizes = useMemo(() => nodeSizes(nodes, baseEdges), [nodes, baseEdges])
  const widths = useMemo(() => Object.fromEntries(Object.entries(sizes).filter(([, s]) => s.width).map(([id, s]) => [id, s.width])), [sizes])

  // Evidenza: con un device, un cavo o un rack selezionato restano in primo piano lui, i suoi cavi e i device
  // collegati; il resto va in dissolvenza
  const focus = useMemo(() => {
    if (selection?.kind === 'edge') {
      const cable = view?.edges.find((e) => e.id === selection.id)
      if (!cable) return null
      return { devices: new Set([String(cable.source), String(cable.target)]), cables: new Set([`cable-${cable.id}`]) }
    }
    const seeds = new Set(selection?.kind === 'node' ? [String(selection.id)] : nodes.filter((n) => n.selected).map((n) => n.id))
    if (seeds.size === 0 && vlanId) {
      // Device con la VLAN su una porta, più quelli in fondo ai cavi che la portano (es. un server senza VLAN documentate)
      const carrying = view.edges.filter((e) => e.vlan_ids.includes(vlanId))
      return {
        devices: new Set([
          ...view.nodes.filter((n) => n.vlan_ids.includes(vlanId)).map((n) => String(n.id)),
          ...carrying.flatMap((e) => [String(e.source), String(e.target)]),
        ]),
        cables: new Set(carrying.map((e) => `cable-${e.id}`)),
        vlan: true,
      }
    }
    if (seeds.size === 0) return null
    const devices = new Set(seeds)
    const cables = new Set()
    for (const e of baseEdges) {
      if (seeds.has(e.source) || seeds.has(e.target)) {
        cables.add(e.id)
        devices.add(e.source)
        devices.add(e.target)
      }
    }
    return { devices, cables }
  }, [selection, nodes, baseEdges, view, vlanId])

  // Un cavo che non cambia resta lo stesso oggetto: React Flow ridisegna solo quelli nuovi (trascinando un device
  // in una mappa con centinaia di cavi cambiano solo i suoi)
  const edgeMemo = useRef(new Map())
  const edges = useMemo(() => {
    const previous = edgeMemo.current
    const next = new Map()
    const list = baseEdges.map((e) => {
      const className = !focus ? e.className
        : !focus.cables.has(e.id) ? `${e.className} cable--faded`
        : focus.vlan ? `${e.className} cable--vlan` : e.className
      const selected = selection?.kind === 'edge' && selection.id === e.data.id
      const geo = geometry[e.id] || null
      const old = previous.get(e.id)
      const edge = old && !selected && !old.selected && old.base === e && old.geo === geo && old.edge.className === className
        ? old.edge
        : {
          ...e,
          className,
          // Il cavo selezionato sta sopra gli altri: le sue maniglie non finiscono sotto un cavo che passa di lì
          zIndex: selected ? 10 : 0,
          data: {
            ...e.data,
            geometry: geo,
            // Cavo selezionato: maniglie per spostarlo
            onRoute: canEdit && selected ? (change) => changeRoute(e.data.id, e.data.flip, change) : null,
          },
        }
      next.set(e.id, { base: e, geo, selected, edge })
      return edge
    })
    edgeMemo.current = next
    return list
  }, [baseEdges, geometry, focus, canEdit, selection, changeRoute])
  // Stesso discorso per i device in dissolvenza (con un device selezionato, cioè anche trascinandolo)
  const fadedMemo = useRef(new WeakMap())
  const displayNodes = useMemo(() => {
    const faded = (node, inFocus) => {
      if (!focus || inFocus) return node
      if (!fadedMemo.current.has(node)) fadedMemo.current.set(node, { ...node, className: 'is-faded' })
      return fadedMemo.current.get(node)
    }
    return [
      ...places.map((b) => faded(b, b.data.ids.some((nodeId) => focus?.devices.has(nodeId)))),
      ...bubbles.map((b) => faded(b, b.data.ids.some((nodeId) => focus?.devices.has(nodeId)))),
      ...nodes.map((n) => {
        const { width, height: minHeight } = sizes[n.id] || {}
        const sized = width === n.data.width && minHeight === n.data.minHeight ? n : { ...n, data: { ...n.data, width, minHeight } }
        return faded(sized, focus?.devices.has(n.id))
      }),
    ]
  }, [places, bubbles, nodes, focus, sizes])
  // Nomi di rack e posizioni, sopra cavi e device (MapLabels)
  const names = useMemo(() => {
    const inFocus = (ids) => !focus || ids.some((nodeId) => focus.devices.has(nodeId))
    return [
      ...places.map((b) => ({
        id: b.id, kind: 'location', x: b.position.x + 12, y: b.position.y + 8, text: b.data.name, depth: b.data.depth,
        title: t('{name}: clic per selezionare i suoi device e spostarli insieme', { name: b.data.path }),
        faded: !inFocus(b.data.ids), onSelect: b.data.onSelect,
      })),
      ...rackLabels.map(({ bubble: b, box }) => ({
        id: b.id, kind: 'rack', x: box.l, y: box.t, text: b.data.name,
        title: t('Rack {name}, {what}: clic per selezionarli e spostarli insieme', {
          name: b.data.name, what: b.data.count === 1 ? t('1 device') : t('{n} device', { n: b.data.count }),
        }),
        faded: !inFocus(b.data.ids), onSelect: b.data.onSelect,
      })),
    ]
  }, [places, rackLabels, focus])
  const selectCable = useCallback((cableId) => setSelection({ kind: 'edge', id: cableId }), [])

  const savePositions = async (list) => {
    setSaving(true)
    try {
      await api.put(
        `/maps/${id}/nodes`,
        list.map((n) => ({ device_id: Number(n.id), x: Math.round(n.position.x), y: Math.round(n.position.y) })),
      )
      await api.put(
        `/maps/${id}/routes`,
        Object.entries(routesRef.current).map(([cableId, route]) => ({ cable_id: Number(cableId), ...route })),
      )
      setDirty(false)
      return true
    } catch (err) {
      setError(err.message)
      return false
    } finally {
      setSaving(false)
    }
  }

  const arrange = () => {
    const heights = Object.fromEntries(nodesRef.current.map((n) => [n.id, n.measured?.height]))
    const options = { withPorts: showLabels, widths }
    const layout = locationsOn
      ? locationLayout(view.nodes, view.edges, view.locations, heights, options)
      : hierarchicalLayout(view.nodes, view.edges, heights, options)
    setNodes((current) => current.map((n) => ({ ...n, position: layout[n.id] ?? n.position })))
    setDirty(true)
    setTimeout(() => fitRef.current({ padding: 0.25, duration: 300 }), 50)
  }

  const addDevice = async (deviceId) => {
    const device = view.available.find((d) => d.id === deviceId)
    if (!device) return
    const current = nodesRef.current
    const bottom = current.length ? Math.max(...current.map((n) => n.position.y)) + Y_GAP : 0
    const next = [...current, { id: String(device.id), type: 'device', position: { x: 0, y: bottom }, data: device }]
    setNodes(next)
    if (await savePositions(next)) await load(true)
  }

  /** Risultato della ricerca: seleziono il cavo della porta trovata (se è in mappa) o il device, e lo porto al centro. */
  const showFound = ({ deviceId, interfaceId, text }) => {
    const cable = interfaceId && view.edges.find((e) => e.source_interface_id === interfaceId || e.target_interface_id === interfaceId)
    setNodes((current) => current.map((n) => (n.selected ? { ...n, selected: false } : n)))
    setSelection(cable ? { kind: 'edge', id: cable.id, found: text } : { kind: 'node', id: deviceId, found: text })
    const node = nodesRef.current.find((n) => n.id === String(deviceId))
    if (node?.measured) {
      setCenter(node.position.x + node.measured.width / 2, node.position.y + node.measured.height / 2, {
        zoom: Math.max(getZoom(), 1),
        duration: 400,
      })
    }
  }

  const removeFromMap = async (deviceId) => {
    const next = nodesRef.current.filter((n) => n.id !== String(deviceId))
    setNodes(next)
    setSelection(null)
    if (await savePositions(next)) await load(true)
  }

  const deleteCable = async (cable) => {
    if (!window.confirm(t('Eliminare questo cavo? Il collegamento sparirà anche dalle schede dei device.'))) return
    try {
      await api.del(`/cables/${cable.id}`)
      invalidate()
      setSelection(null)
      await load(true)
    } catch (err) {
      setError(err.message)
    }
  }

  /** PNG o SVG di tutta la mappa (non solo della parte visibile), con lo sfondo del tema. */
  const exportImage = async (format) => {
    const flowNodes = getNodes()
    if (flowNodes.length === 0) return
    const bounds = getNodesBounds(flowNodes)
    const width = Math.ceil(bounds.width + EXPORT_PADDING * 2)
    const height = Math.ceil(bounds.height + EXPORT_PADDING * 2)
    const element = document.querySelector('.map-canvas .react-flow__viewport')
    const background = getComputedStyle(document.body).getPropertyValue('--surface-2').trim() || '#ffffff'
    const options = {
      backgroundColor: background,
      // I pallini per collegare i device servono solo a modificare la mappa
      filter: (node) => !node.classList?.contains('react-flow__handle') && !node.classList?.contains('cable-handles'),
      width,
      height,
      style: {
        width: `${width}px`,
        height: `${height}px`,
        transform: `translate(${EXPORT_PADDING - bounds.x}px, ${EXPORT_PADDING - bounds.y}px) scale(1)`,
      },
    }
    try {
      const dataUrl = format === 'svg' ? await toSvg(element, options) : await toPng(element, { ...options, pixelRatio: 2 })
      download(dataUrl, `${view.map.name}.${format}`)
    } catch (err) {
      setError(t('Esportazione non riuscita: {error}', { error: err.message || err }))
    }
  }

  const print = () => {
    setSelection(null)
    fitRef.current({ padding: 0.08 })
    setTimeout(() => window.print(), 350)
  }

  const exportAs = (value) => {
    if (value === 'print') print()
    else if (value) exportImage(value)
  }

  const checkNow = async (deviceId) => {
    setChecking(true)
    try {
      await api.post(`/devices/${deviceId}/check`)
      await load(true)
    } catch (err) {
      setError(err.message)
    } finally {
      setChecking(false)
    }
  }

  if (!view) {
    return (
      <div className="map-page">
        <div className="map-message">{error ? <p className="error-box">{error}</p> : <p className="muted">{t('Caricamento mappa…')}</p>}</div>
      </div>
    )
  }

  const nameOf = Object.fromEntries(view.nodes.map((n) => [n.id, n.name]))
  const selectedNode = selection?.kind === 'node' ? view.nodes.find((n) => n.id === selection.id) : null
  const selectedEdge = selection?.kind === 'edge' ? view.edges.find((e) => e.id === selection.id) : null

  return (
    <div className="map-page">
      <div className="map-toolbar">
        <div className="map-toolbar__title">
          <Link to="/maps" className="crumbs">{t('Mappe')}</Link>
          <h1>{view.map.name}</h1>
          <span className="muted">
            <RefLabel resource="sites" id={view.map.site_id} />
            {view.map.location_id && (
              <>
                {', '}
                <RefLabel resource="locations" id={view.map.location_id} />
              </>
            )}
          </span>
        </div>
        <div className="map-toolbar__actions">
          {liveCount(view.nodes)}
          {view.nodes.length > 0 && <MapSearch nodes={view.nodes} onPick={showFound} />}
          {view.vlans.length > 0 && (
            <select className="input input--sm" value={vlanId ?? ''} aria-label={t('Evidenzia una VLAN')}
              onChange={(e) => {
                setSelection(null)
                setVlanId(e.target.value ? Number(e.target.value) : null)
              }}>
              <option value="">{t('Tutte le VLAN')}</option>
              {view.vlans.map((v) => (
                <option key={v.id} value={v.id}>VLAN {v.vid} · {v.name}</option>
              ))}
            </select>
          )}
          {canEdit && !view.map.auto_include && view.available.length > 0 && (
            <select className="input input--sm" value="" onChange={(e) => e.target.value && addDevice(Number(e.target.value))} aria-label={t('Aggiungi un device alla mappa')}>
              <option value="">{t('Aggiungi device…')}</option>
              {view.available.map((d) => (
                <option key={d.id} value={d.id}>{d.name}</option>
              ))}
            </select>
          )}
          <label className="check check--inline">
            <input type="checkbox" checked={showLabels} onChange={(e) => setShowLabels(e.target.checked)} />
            {t('Nomi delle porte')}
          </label>
          {view.locations.length > 0 && (
            <label className="check check--inline" title={t('Edifici, piani e stanze come riquadri colorati; "Disponi" raggruppa i device per posizione')}>
              <input type="checkbox" checked={showLocations} onChange={(e) => {
                  setShowLocations(e.target.checked)
                  try {
                    localStorage.setItem(LOCATIONS_PREF, e.target.checked ? '1' : '0')
                  } catch {
                    // senza localStorage la scelta vale solo per questa pagina
                  }
                }} />
              {t('Posizioni')}
            </label>
          )}
          <IconButton icon="refresh" label={reloading ? t('Aggiornamento…') : t('Aggiorna la mappa (device, cavi e stato)')} small
            onClick={reload} disabled={reloading} />
          <select className="input input--sm" value="" onChange={(e) => exportAs(e.target.value)} aria-label={t('Esporta o stampa la mappa')}
            disabled={view.nodes.length === 0}>
            <option value="">{t('Esporta…')}</option>
            <option value="png">{t('Immagine PNG')}</option>
            <option value="svg">{t('Disegno SVG')}</option>
            <option value="print">{t('Stampa o PDF')}</option>
          </select>
          {canEdit && (
            <>
              <IconButton icon="layout" label={t('Disponi automaticamente')} small onClick={arrange} disabled={view.nodes.length === 0} />
              <IconButton icon="save" label={saving ? t('Salvataggio…') : dirty ? t('Salva disposizione') : t('Disposizione salvata')} small
                className="btn--primary" onClick={() => savePositions(nodesRef.current)} disabled={!dirty || saving}>
                {dirty && <span className="btn__dot" aria-hidden="true" />}
              </IconButton>
            </>
          )}
        </div>
      </div>

      {error && <p className="error-box map-error" role="alert">{error}</p>}

      <div className="map-canvas">
        <ReactFlow
          nodes={displayNodes}
          edges={edges}
          nodeTypes={nodeTypes}
          edgeTypes={edgeTypes}
          onNodesChange={onNodesChange}
          onNodeDragStop={onNodeDragStop}
          onNodeClick={onNodeClick}
          onEdgeClick={onEdgeClick}
          onPaneClick={onPaneClick}
          onConnect={onConnect}
          nodesConnectable={canEdit}
          connectionMode={ConnectionMode.Loose}
          deleteKeyCode={null}
          minZoom={0.15}
          maxZoom={2}
          colorMode={theme}
        >
          <Background variant={BackgroundVariant.Dots} gap={22} size={1.2} />
          <MapLabels edges={edges} geometry={geometry} names={names} onSelectEdge={selectCable} />
          <Controls showInteractive={false} />
          <MiniMap pannable zoomable nodeColor={(n) => (n.type === 'rack' || n.type === 'location' ? 'transparent' : n.data.color)} nodeStrokeWidth={2} />
          <Panel position="bottom-center">
            <Legend edges={view.edges} nodes={view.nodes} racks={view.nodes.some((n) => n.rack_id)} locations={locationsOn}
              vlan={view.vlans.find((v) => v.id === vlanId)} cableTypes={cableTypes} onCableTypes={setCableTypes} />
          </Panel>
          {canEdit && hint && view.nodes.length > 0 && (
            <Panel position="top-left" className="map-hint">
              {t("Per collegare due device passa sopra uno dei due e trascina da un suo pallino all'altro.")}
              <button type="button" className="map-hint__close" onClick={() => setHint(false)} aria-label={t('Chiudi')} title={t('Chiudi')}>×</button>
            </Panel>
          )}
        </ReactFlow>

        {view.nodes.length === 0 && (
          <div className="map-message">
            {view.map.auto_include ? (
              <p>
                In questa sede non ci sono ancora device. <Link to="/devices">{t('Aggiungine uno')}</Link> e torna qui.
              </p>
            ) : (
              <p>{t('La mappa è vuota: scegli i device da "Aggiungi device…" in alto.')}</p>
            )}
          </div>
        )}

        {selectedNode && (
          <aside className="map-panel" aria-label={t('Dettagli device')}>
            <button type="button" className="modal__close" onClick={() => setSelection(null)} aria-label={t('Chiudi dettagli')}>{t('×')}</button>
            <h2>{selectedNode.name}</h2>
            {selection.found && <p className="map-found"><span className="muted">{t('Trovato:')}</span> <span className="mono">{selection.found}</span></p>}
            <dl className="facts facts--stack">
              <div><dt>{t('Ruolo')}</dt><dd>{selectedNode.role || '—'}</dd></div>
              <div><dt>{t('Stato')}</dt><dd><Badge value={selectedNode.status} options={DEVICE_STATUS} /></dd></div>
              <div><dt>{t('IP di management')}</dt><dd className="mono">{selectedNode.primary_ip || '—'}</dd></div>
              {selectedNode.primary_ip && (
                <div>
                  <dt>{t('Stato live')}</dt>
                  <dd>{selectedNode.reachable === null ? <span className="muted">{t('Non ancora controllato')}</span> : <LiveStatus device={selectedNode} long />}</dd>
                </div>
              )}
              <div><dt>{t('Collegamenti in mappa')}</dt><dd>{view.edges.filter((e) => e.source === selectedNode.id || e.target === selectedNode.id).length}</dd></div>
            </dl>
            <div className="map-panel__actions">
              <IconLink icon="open" label={t('Apri scheda del device')} small className="btn--primary" to={`/devices/${selectedNode.id}`} />
              {canEdit && selectedNode.primary_ip && (
                <IconButton icon="refresh" label={checking ? t('Controllo in corso…') : t('Controlla ora (ping e SNMP)')} small
                  className={checking ? 'is-spinning' : ''} disabled={checking} onClick={() => checkNow(selectedNode.id)} />
              )}
              {canEdit && !view.map.auto_include && (
                <IconButton icon="eyeOff" label={t('Togli dalla mappa (il device resta)')} small className="btn--ghost"
                  onClick={() => removeFromMap(selectedNode.id)} />
              )}
            </div>
          </aside>
        )}

        {selectedEdge && (
          <aside className="map-panel" aria-label={t('Dettagli collegamento')}>
            <button type="button" className="modal__close" onClick={() => setSelection(null)} aria-label={t('Chiudi dettagli')}>{t('×')}</button>
            <h2>{t('Collegamento')}</h2>
            {selection.found && <p className="map-found"><span className="muted">{t('Trovato:')}</span> <span className="mono">{selection.found}</span></p>}
            <p className="cable-ends">
              <Link to={`/devices/${selectedEdge.source}`}>{nameOf[selectedEdge.source]}</Link> <span className="mono">{selectedEdge.source_interface}</span>
              <span className="cable-ends__line" style={{ background: cableStyle(selectedEdge.type).color }} aria-hidden="true" />
              <Link to={`/devices/${selectedEdge.target}`}>{nameOf[selectedEdge.target]}</Link> <span className="mono">{selectedEdge.target_interface}</span>
            </p>
            <dl className="facts facts--stack">
              <div><dt>{t('Tipo')}</dt><dd>{selectedEdge.type ? labelOf(CABLE_TYPES, selectedEdge.type) : t('Non indicato')}</dd></div>
              <div><dt>{t('Stato')}</dt><dd>{labelOf(CABLE_STATUS, selectedEdge.status)}</dd></div>
              <div><dt>{t('Velocità porta')}</dt><dd>{formatSpeed(selectedEdge.speed_mbps)}</dd></div>
            </dl>
            {canEdit && (
              <p className="hint map-panel__hint">
                {t('Trascina le barrette per spostare i tratti del cavo e i pallini alle estremità per cambiare dove si attacca al device. Poi salva la disposizione.')}
              </p>
            )}
            {canEdit && (
              <div className="map-panel__actions">
                {routes[selectedEdge.id] && (
                  <IconButton icon="layout" label={t('Torna al percorso automatico')} small
                    onClick={() => changeRoute(selectedEdge.id, false, { reset: true })} />
                )}
                <IconButton icon="trash" label={t('Elimina cavo')} small danger className="btn--ghost" onClick={() => deleteCable(selectedEdge)} />
              </div>
            )}
          </aside>
        )}
      </div>

      {connecting && (
        <CableDialog
          aDeviceId={connecting.a}
          bDeviceId={connecting.b}
          onClose={() => setConnecting(null)}
          onCreated={async () => {
            setConnecting(null)
            await load(true)
          }}
        />
      )}
    </div>
  )
}

/** "3 su 4 rispondono" nella barra della mappa (solo device controllati dal monitor) */
function liveCount(nodes) {
  const checked = nodes.filter((n) => n.reachable !== null && n.reachable !== undefined)
  if (checked.length === 0) return null
  const down = checked.filter((n) => !n.reachable).length
  return (
    <span className={`map-live${down ? ' map-live--down' : ''}`}>
      <span className={`live-dot live-dot--${down ? 'down' : 'up'}`} />
      {down ? t('{down} su {n} non rispondono', { down, n: checked.length }) : t('Tutti i {n} device rispondono', { n: checked.length })}
    </span>
  )
}

export default function MapEditor() {
  return (
    <ReactFlowProvider>
      <Editor />
    </ReactFlowProvider>
  )
}
