import { memo } from 'react'
import { ViewportPortal } from '@xyflow/react'
import { LABEL_H, labelLength } from './geometry'

/** Nome di una porta: riquadro con il testo, ruotato se il cavo esce da sopra o da sotto il device. */
function PortLabel({ x, y, text, title, vertical }) {
  const width = labelLength(text)
  return (
    <g className="port-label" transform={`translate(${x} ${y})${vertical ? ' rotate(-90)' : ''}`}>
      {title && title !== text && <title>{title}</title>}
      <rect className="react-flow__edge-textbg" x={-width / 2} y={-LABEL_H / 2} width={width} height={LABEL_H} rx={3} />
      <text className="react-flow__edge-text" textAnchor="middle" dominantBaseline="central">{text}</text>
    </g>
  )
}

// Un gruppo per cavo, che resta uguale se il cavo non cambia (trascinando un device si ridisegnano solo i suoi)
const CableLabels = memo(function CableLabels({ cableId, labels, faded, onSelect }) {
  return (
    <g className={faded ? 'port-labels port-labels--faded' : 'port-labels'} onClick={(e) => {
        e.stopPropagation()
        onSelect(cableId)
      }}>
      {labels.map((l, i) => <PortLabel key={i} {...l} />)}
    </g>
  )
})

/**
 * Nomi sopra tutto il resto della mappa: i nomi delle porte sopra i cavi (prima ogni cavo poteva coprire i nomi
 * di quelli disegnati prima), i nomi dei rack e delle posizioni sopra cavi e nomi delle porte. Posizioni calcolate
 * da MapEditor (map/geometry.js per le porte, rackNames/locationBubbles per gli altri).
 * edges: i cavi della mappa (className con cable--faded), names: [{ id, kind, x, y, text, title, depth, faded, ids, onSelect }];
 * onDragGroup(ids, evento): tenendo premuto sul nome e trascinando si spostano insieme tutti i device (ids).
 */
function MapLabels({ edges, geometry, names, onSelectEdge, onDragGroup }) {
  return (
    <ViewportPortal>
      <svg className="map-labels" aria-hidden="true">
        {edges.map((e) => {
          const labels = geometry[e.id]?.labels
          if (!labels?.length) return null
          return <CableLabels key={e.id} cableId={e.data.id} labels={labels} faded={e.className.includes('cable--faded')} onSelect={onSelectEdge} />
        })}
      </svg>
      {names.map((n) => (
        <button key={n.id} type="button"
          className={`map-name map-name--${n.kind} nodrag nopan${n.kind === 'location' ? ` loc-bubble--d${Math.min(n.depth, 3)}` : ''}${n.faded ? ' map-name--faded' : ''}`}
          style={{ transform: `translate(${n.x}px, ${n.y}px)` }} title={n.title}
          onPointerDown={(e) => onDragGroup(n.ids, e)} onClick={(e) => {
            e.stopPropagation()
            n.onSelect()
          }}>
          {n.text}
        </button>
      ))}
    </ViewportPortal>
  )
}

export default memo(MapLabels)
