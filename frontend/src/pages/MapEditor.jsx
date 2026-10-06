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
import { Badge, LiveStatus } from '../components/Bits'
import CableDialog from '../components/CableDialog'
import { IconButton, IconLink } from '../components/Icon'
import RefLabel from '../components/RefLabel'
import { invalidate } from '../hooks'
import CableEdge from '../map/CableEdge'
import { cableStyle } from '../map/cables'
import { cableGeometry } from '../map/geometry'
import DeviceNode from '../map/DeviceNode'
import RackNode from '../map/RackNode'
import { X_GAP, Y_GAP, effectiveLevels, hierarchicalLayout } from '../map/layout'
import { CABLE_STATUS, CABLE_TYPES, DEVICE_STATUS, formatSpeed, labelOf } from '../options'

const nodeTypes = { device: DeviceNode, rack: RackNode }
const edgeTypes = { cable: CableEdge }
const EDGE_STYLE_KEY = 'netmap.map.edgeStyle'

/** Cavi ad angolo (predefinito) o dritti: preferenza di chi guarda, salvata nel browser. */
function useEdgeStyle() {
  const [value, setValue] = useState(() => {
    try {
      return localStorage.getItem(EDGE_STYLE_KEY) === 'straight' ? 'straight' : 'bus'
    } catch {
      return 'bus'
    }
  })
  const change = (next) => {
    setValue(next)
    try {
      localStorage.setItem(EDGE_STYLE_KEY, next)
    } catch {
      // senza storage la scelta vale solo per questa pagina
    }
  }
  return [value, change]
}
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

function toFlowEdge(edge, levelOf, showLabels, selected, mode) {
  // Il cavo parte sempre dal device più in alto nella gerarchia
  const flip = (levelOf[edge.source] ?? 0) > (levelOf[edge.target] ?? 0)
  const style = cableStyle(edge.type)
  const fast = (edge.speed_mbps || 0) >= 10000
  return {
    id: `cable-${edge.id}`,
    source: String(flip ? edge.target : edge.source),
    target: String(flip ? edge.source : edge.target),
    type: 'cable',
    data: {
      ...edge,
      mode,
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

function Legend({ edges, nodes, racks }) {
  const types = [...new Set(edges.map((e) => e.type || ''))]
  const planned = edges.some((e) => e.status === 'planned')
  const live = nodes.some((n) => n.reachable !== null && n.reachable !== undefined)
  if (types.length === 0 && !live && !racks) return null
  return (
    <div className="map-legend">
      {racks && <span className="map-legend__item"><span className="map-legend__rack" />Rack</span>}
      {live && (
        <>
          <span className="map-legend__item"><span className="live-dot live-dot--up" />Risponde</span>
          <span className="map-legend__item"><span className="live-dot live-dot--down" />Non risponde</span>
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
          Pianificato
        </span>
      )}
    </div>
  )
}

function Editor() {
  const { id } = useParams()
  const { canEdit } = useAuth()
  const { fitView, getNodes } = useReactFlow()
  const [view, setView] = useState(null)
  const [error, setError] = useState(null)
  const [nodes, setNodes, onNodesChange] = useNodesState([])
  const [dirty, setDirty] = useState(false)
  const [saving, setSaving] = useState(false)
  const [showLabels, setShowLabels] = useState(false)
  const [edgeStyle, setEdgeStyle] = useEdgeStyle()
  const [selection, setSelection] = useState(null) // { kind: 'node' | 'edge', id }
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
      (view?.edges || []).map((e) => toFlowEdge(e, levelOf, showLabels, selection?.kind === 'edge' && selection.id === e.id, edgeStyle)),
    [view, levelOf, showLabels, selection, edgeStyle],
  )

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
  const geometry = useMemo(() => cableGeometry(nodes, bubbles, baseEdges, edgeStyle), [nodes, bubbles, baseEdges, edgeStyle])

  // Evidenza: con un device, un cavo o un rack selezionato restano in primo piano lui, i suoi cavi e i device
  // collegati; il resto va in dissolvenza
  const focus = useMemo(() => {
    if (selection?.kind === 'edge') {
      const cable = view?.edges.find((e) => e.id === selection.id)
      if (!cable) return null
      return { devices: new Set([String(cable.source), String(cable.target)]), cables: new Set([`cable-${cable.id}`]) }
    }
    const seeds = new Set(selection?.kind === 'node' ? [String(selection.id)] : nodes.filter((n) => n.selected).map((n) => n.id))
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
  }, [selection, nodes, baseEdges, view])

  const edges = useMemo(
    () =>
      baseEdges.map((e) => ({
        ...e,
        className: focus && !focus.cables.has(e.id) ? `${e.className} cable--faded` : e.className,
        data: { ...e.data, geometry: geometry[e.id] || null },
      })),
    [baseEdges, geometry, focus],
  )
  const displayNodes = useMemo(() => {
    const faded = (node, inFocus) => (focus && !inFocus ? { ...node, className: 'is-faded' } : node)
    return [
      ...bubbles.map((b) => faded(b, b.data.ids.some((nodeId) => focus?.devices.has(nodeId)))),
      ...nodes.map((n) => faded(n, focus?.devices.has(n.id))),
    ]
  }, [bubbles, nodes, focus])

  const savePositions = async (list) => {
    setSaving(true)
    try {
      await api.put(
        `/maps/${id}/nodes`,
        list.map((n) => ({ device_id: Number(n.id), x: Math.round(n.position.x), y: Math.round(n.position.y) })),
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
    const layout = hierarchicalLayout(view.nodes, view.edges, heights, { withPorts: showLabels })
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

  const removeFromMap = async (deviceId) => {
    const next = nodesRef.current.filter((n) => n.id !== String(deviceId))
    setNodes(next)
    setSelection(null)
    if (await savePositions(next)) await load(true)
  }

  const deleteCable = async (cable) => {
    if (!window.confirm('Eliminare questo cavo? Il collegamento sparirà anche dalle schede dei device.')) return
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
      filter: (node) => !node.classList?.contains('react-flow__handle'),
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
      setError(`Esportazione non riuscita: ${err.message || err}`)
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
        <div className="map-message">{error ? <p className="error-box">{error}</p> : <p className="muted">Caricamento mappa…</p>}</div>
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
          <Link to="/maps" className="crumbs">Mappe</Link>
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
          {canEdit && !view.map.auto_include && view.available.length > 0 && (
            <select className="input input--sm" value="" onChange={(e) => e.target.value && addDevice(Number(e.target.value))} aria-label="Aggiungi un device alla mappa">
              <option value="">Aggiungi device…</option>
              {view.available.map((d) => (
                <option key={d.id} value={d.id}>{d.name}</option>
              ))}
            </select>
          )}
          <select className="input input--sm" value={edgeStyle} onChange={(e) => setEdgeStyle(e.target.value)} aria-label="Forma dei cavi">
            <option value="bus">Cavi ad angolo</option>
            <option value="straight">Cavi dritti</option>
          </select>
          <label className="check check--inline">
            <input type="checkbox" checked={showLabels} onChange={(e) => setShowLabels(e.target.checked)} />
            Nomi delle porte
          </label>
          <select className="input input--sm" value="" onChange={(e) => exportAs(e.target.value)} aria-label="Esporta o stampa la mappa"
            disabled={view.nodes.length === 0}>
            <option value="">Esporta…</option>
            <option value="png">Immagine PNG</option>
            <option value="svg">Disegno SVG</option>
            <option value="print">Stampa o PDF</option>
          </select>
          {canEdit && (
            <>
              <IconButton icon="layout" label="Disponi automaticamente" small onClick={arrange} disabled={view.nodes.length === 0} />
              <IconButton icon="save" label={saving ? 'Salvataggio…' : dirty ? 'Salva disposizione' : 'Disposizione salvata'} small
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
          colorMode="system"
        >
          <Background variant={BackgroundVariant.Dots} gap={22} size={1.2} />
          <Controls showInteractive={false} />
          <MiniMap pannable zoomable nodeColor={(n) => (n.type === 'rack' ? 'transparent' : n.data.color)} nodeStrokeWidth={2} />
          <Panel position="bottom-center">
            <Legend edges={view.edges} nodes={view.nodes} racks={view.nodes.some((n) => n.rack_id)} />
          </Panel>
          {canEdit && view.nodes.length > 0 && (
            <Panel position="top-left" className="map-hint">
              Per collegare due device passa sopra uno dei due e trascina da un suo pallino all'altro.
            </Panel>
          )}
        </ReactFlow>

        {view.nodes.length === 0 && (
          <div className="map-message">
            {view.map.auto_include ? (
              <p>
                In questa sede non ci sono ancora device. <Link to="/devices">Aggiungine uno</Link> e torna qui.
              </p>
            ) : (
              <p>La mappa è vuota: scegli i device da "Aggiungi device…" in alto.</p>
            )}
          </div>
        )}

        {selectedNode && (
          <aside className="map-panel" aria-label="Dettagli device">
            <button type="button" className="modal__close" onClick={() => setSelection(null)} aria-label="Chiudi dettagli">×</button>
            <h2>{selectedNode.name}</h2>
            <dl className="facts facts--stack">
              <div><dt>Ruolo</dt><dd>{selectedNode.role || '—'}</dd></div>
              <div><dt>Stato</dt><dd><Badge value={selectedNode.status} options={DEVICE_STATUS} /></dd></div>
              <div><dt>IP di management</dt><dd className="mono">{selectedNode.primary_ip || '—'}</dd></div>
              {selectedNode.primary_ip && (
                <div>
                  <dt>Stato live</dt>
                  <dd>{selectedNode.reachable === null ? <span className="muted">Non ancora controllato</span> : <LiveStatus device={selectedNode} long />}</dd>
                </div>
              )}
              <div><dt>Collegamenti in mappa</dt><dd>{view.edges.filter((e) => e.source === selectedNode.id || e.target === selectedNode.id).length}</dd></div>
            </dl>
            <div className="map-panel__actions">
              <IconLink icon="open" label="Apri scheda del device" small className="btn--primary" to={`/devices/${selectedNode.id}`} />
              {canEdit && selectedNode.primary_ip && (
                <IconButton icon="refresh" label={checking ? 'Controllo in corso…' : 'Controlla ora (ping e SNMP)'} small
                  className={checking ? 'is-spinning' : ''} disabled={checking} onClick={() => checkNow(selectedNode.id)} />
              )}
              {canEdit && !view.map.auto_include && (
                <IconButton icon="eyeOff" label="Togli dalla mappa (il device resta)" small className="btn--ghost"
                  onClick={() => removeFromMap(selectedNode.id)} />
              )}
            </div>
          </aside>
        )}

        {selectedEdge && (
          <aside className="map-panel" aria-label="Dettagli collegamento">
            <button type="button" className="modal__close" onClick={() => setSelection(null)} aria-label="Chiudi dettagli">×</button>
            <h2>Collegamento</h2>
            <p className="cable-ends">
              <Link to={`/devices/${selectedEdge.source}`}>{nameOf[selectedEdge.source]}</Link> <span className="mono">{selectedEdge.source_interface}</span>
              <span className="cable-ends__line" style={{ background: cableStyle(selectedEdge.type).color }} aria-hidden="true" />
              <Link to={`/devices/${selectedEdge.target}`}>{nameOf[selectedEdge.target]}</Link> <span className="mono">{selectedEdge.target_interface}</span>
            </p>
            <dl className="facts facts--stack">
              <div><dt>Tipo</dt><dd>{selectedEdge.type ? labelOf(CABLE_TYPES, selectedEdge.type) : 'Non indicato'}</dd></div>
              <div><dt>Stato</dt><dd>{labelOf(CABLE_STATUS, selectedEdge.status)}</dd></div>
              <div><dt>Velocità porta</dt><dd>{formatSpeed(selectedEdge.speed_mbps)}</dd></div>
            </dl>
            {canEdit && (
              <div className="map-panel__actions">
                <IconButton icon="trash" label="Elimina cavo" small danger className="btn--ghost" onClick={() => deleteCable(selectedEdge)} />
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
      {down ? `${down} su ${checked.length} non rispondono` : `Tutti i ${checked.length} device rispondono`}
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
