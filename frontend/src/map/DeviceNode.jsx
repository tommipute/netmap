import { memo } from 'react'
import { Handle, Position } from '@xyflow/react'
import { DEVICE_STATUS, labelOf } from '../options'

function DeviceNode({ data, selected }) {
  const ip = data.primary_ip ? data.primary_ip.split('/')[0] : null
  const live = data.reachable === true ? 'up' : data.reachable === false ? 'down' : null
  // Con lo stato live il pallino dice se risponde; senza, mostra lo stato documentato
  const dot = live ? (
    <span className={`live-dot live-dot--${live}`} title={live === 'up' ? 'Risponde' : 'Non risponde'} />
  ) : (
    <span className={`status-dot status-dot--${data.status}`} title={labelOf(DEVICE_STATUS, data.status)} />
  )
  return (
    <div className={`dnode${selected ? ' dnode--selected' : ''}${live === 'down' ? ' dnode--down' : ''}`} style={{ '--role': data.color }}>
      <Handle type="target" position={Position.Top} className="dnode__handle" />
      <div className="dnode__name">
        {dot}
        {data.name}
      </div>
      <div className="dnode__role">{data.role || 'Senza ruolo'}</div>
      {ip && <div className="dnode__ip">{ip}</div>}
      <Handle type="source" position={Position.Bottom} className="dnode__handle" />
    </div>
  )
}

export default memo(DeviceNode)
