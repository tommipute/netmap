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
import { cableGeometry, nodeWidths } from '../map/geometry'
import DeviceNode from '../map/DeviceNode'
import MapSearch from '../map/MapSearch'
import RackNode from '../map/RackNode'
import { X_GAP, Y_GAP, effectiveLevels, hierarchicalLayout } from '../map/layout'
import { CABLE_STATUS, CABLE_TYPES, DEVICE_STATUS, formatSpeed, labelOf } from '../options'
import { t } from '../i18n'

const nodeTypes = { device: DeviceNode, rack: RackNode }
const edgeTypes = { cable: CableEdge }
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

/** Nodi per React Flow: posizione attuale > posizione salvata > calcolata. */
function buildFlowNodes(view, previous) {
  const known = new Map(previous.map((n) => [n.id, n.position]))
  const nodes = view.nodes.map((n) => {
    const id = String(n.id)
    const position = known.get(id) ?? (n.x !== null && n.y !== null ? { x: n.x, y: n.y } : null)
    return { id, type: 'device', position, data: n }
  })
  const missing = nodes.filter((n) => !n.position)
  if (missing.length === 0) return { nodes, changed: false }

  if (missing.length === nodes.length) {
    const layout = hierarchicalLayout(view.nodes, view.edges)
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

/** Nome del rack in basso a sinistra; se lì passa un cavo e a destra no, va a destra. */
function labelSide(bubble, geometry) {
  const zone = (left) => {
    const width = Math.min(bubble.width / 2, 120)
    const l = left ? bubble.position.x + 6 : bubble.position.x + bubble.width - 6 - width
    return { l, r: l + width, t: bubble.position.y + bubble.height - 26, b: bubble.position.y + bubble.height }
  }
  const busy = (box) => Object.values(geometry).some((g) => g.points.some((p, i) => i > 0 && crosses(g.points[i - 1], p, box)))
  return busy(zone(true)) && !busy(zone(false)) ? 'right' : 'left'
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
    const others = measured.filter((n) => n.data.rack_id !== rackId)
    let clusters = members.map((n) => [n])
    for (;;) {
      let best = null
      for (let i = 0; i < clusters.length; i++) {
        for (let j = i + 1; j < clusters.length; j++) {
          const box = bubbleBox([...clusters[i], ...clusters[j]])
          if (others.some((n) => overlaps(box, n))) continue
          const area = (box.r - box.l) * (box.b - box.t)
          if (!best || area < best.area) best = { i, j, area }
        }
      }
      if (!best) break
      clusters[best.i] = [...clusters[best.i], ...clusters[best.j]]
      clusters = clusters.filter((_, k) => k !== best.j)
    }
    const allIds = members.map((n) => n.id)
    clusters.forEach((cluster, k) => {
      const box = bubbleBox(cluster)
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
      // Nomi delle porte, ognuno vicino al suo device
      sourceLabel: showLabels ? (flip ? edge.target_interface : edge.source_interface) : null,
      targetLabel: showLabels ? (flip ? edge.source_interface : edge.target_interface) : null,
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

function Legend({ edges, nodes, racks, vlan }) {
  const types = [...new Set(edges.map((e) => e.type || ''))]
  const planned = edges.some((e) => e.status === 'planned')
  const live = nodes.some((n) => n.reachable !== null && n.reachable !== undefined)
  if (types.length === 0 && !live && !racks && !vlan) return null
  return (
    <div className="map-legend">
      {vlan && <span className="map-legend__item"><span className="map-legend__line map-legend__line--vlan" />VLAN {vlan.vid} {vlan.name}</span>}
      {racks && <span className="map-legend__item"><span className="map-legend__rack" />{t('Rack')}</span>}
      {live && (
        <>
          <span className="map-legend__item"><span className="live-dot live-dot--up" />{t('Risponde')}</span>
          <span className="map-legend__item"><span className="live-dot live-dot--down" />{t('Non risponde')}</span>
        </>
      )}
      {types.map((type) => {
        const style = cableStyle(type || null)
        return (
          <span key={type || 'none'} className="map-legend__item">
            <span className="map-legend__line" style={{ background: style.color }} />
            {style.label}
          </span>
        )
      })}
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
        setView(data)
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
      (view?.edges || []).map((e) =>
        toFlowEdge(e, levelOf, showLabels, selection?.kind === 'edge' && selection.id === e.id, routes[e.id])),
    [view, levelOf, showLabels, selection, routes],
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
  const bubbles = useMemo(() => rackBubbles(nodes, selectRack), [nodes, selectRack])
  // Percorsi ed etichette di tutti i cavi: dipendono dalle posizioni, si ricalcolano mentre si sposta un device
  const geometry = useMemo(() => cableGeometry(nodes, bubbles, baseEdges), [nodes, bubbles, baseEdges])
  // Con i nomi delle porte un device con tanti cavi sullo stesso lato si allarga quanto serve
  const widths = useMemo(() => nodeWidths(nodes, baseEdges), [nodes, baseEdges])

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

  const edges = useMemo(
    () =>
      baseEdges.map((e) => ({
        ...e,
        className: !focus ? e.className
          : !focus.cables.has(e.id) ? `${e.className} cable--faded`
          : focus.vlan ? `${e.className} cable--vlan` : e.className,
        // Il cavo selezionato sta sopra gli altri: le sue maniglie non finiscono sotto un cavo che passa di lì
        zIndex: selection?.kind === 'edge' && selection.id === e.data.id ? 10 : 0,
        data: {
          ...e.data,
          geometry: geometry[e.id] || null,
          // Cavo selezionato: maniglie per spostarlo
          onRoute: canEdit && selection?.kind === 'edge' && selection.id === e.data.id
            ? (change) => changeRoute(e.data.id, e.data.flip, change) : null,
        },
      })),
    [baseEdges, geometry, focus, canEdit, selection, changeRoute],
  )
  const displayNodes = useMemo(() => {
    const faded = (node, inFocus) => (focus && !inFocus ? { ...node, className: 'is-faded' } : node)
    return [
      ...bubbles.map((b) => {
        const side = labelSide(b, geometry)
        const placed = side === 'left' ? b : { ...b, data: { ...b.data, labelSide: side } }
        return faded(placed, b.data.ids.some((nodeId) => focus?.devices.has(nodeId)))
      }),
      ...nodes.map((n) => {
        const width = widths[n.id]
        const sized = width === n.data.width ? n : { ...n, data: { ...n.data, width } }
        return faded(sized, focus?.devices.has(n.id))
      }),
    ]
  }, [bubbles, nodes, focus, widths, geometry])

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
    const layout = hierarchicalLayout(view.nodes, view.edges, heights, { withPorts: showLabels, widths })
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
          onNodeDragStop={() => setDirty(true)}
          onNodeClick={(_, node) => node.type === 'device' && setSelection({ kind: 'node', id: Number(node.id) })}
          onEdgeClick={(_, edge) => setSelection({ kind: 'edge', id: edge.data.id })}
          onPaneClick={() => setSelection(null)}
          onConnect={({ source, target }) => source !== target && setConnecting({ a: Number(source), b: Number(target) })}
          nodesConnectable={canEdit}
          connectionMode={ConnectionMode.Loose}
          deleteKeyCode={null}
          minZoom={0.15}
          maxZoom={2}
          colorMode={theme}
        >
          <Background variant={BackgroundVariant.Dots} gap={22} size={1.2} />
          <Controls showInteractive={false} />
          <MiniMap pannable zoomable nodeColor={(n) => (n.type === 'rack' ? 'transparent' : n.data.color)} nodeStrokeWidth={2} />
          <Panel position="bottom-center">
            <Legend edges={view.edges} nodes={view.nodes} racks={view.nodes.some((n) => n.rack_id)}
              vlan={view.vlans.find((v) => v.id === vlanId)} />
          </Panel>
          {canEdit && view.nodes.length > 0 && (
            <Panel position="top-left" className="map-hint">
              {t("Per collegare due device passa sopra uno dei due e trascina da un suo pallino all'altro.")}
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
