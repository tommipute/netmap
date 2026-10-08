import { memo } from 'react'
import { Handle, Position } from '@xyflow/react'
import { DEVICE_STATUS, labelOf } from '../options'
import { t } from '../i18n'

function DeviceNode({ data, selected }) {
  const ip = data.primary_ip ? data.primary_ip.split('/')[0] : null
  const live = data.reachable === true ? 'up' : data.reachable === false ? 'down' : null
  // Con lo stato live il pallino dice se risponde; senza, mostra lo stato documentato
  const dot = live ? (
    <span className={`live-dot live-dot--${live}`} title={live === 'up' ? t('Risponde') : t('Non risponde')} />
  ) : (
    <span className={`status-dot status-dot--${data.status}`} title={labelOf(DEVICE_STATUS, data.status)} />
  )
  return (
    <div className={`dnode${selected ? ' dnode--selected' : ''}`} style={{ '--role': data.color, width: data.width }}>
      {/* Pallini per collegare due device trascinando: i cavi invece si attaccano dove serve (map/anchors.js) */}
      <Handle type="target" id="t" position={Position.Top} className="dnode__handle" />
      <Handle type="source" id="l" position={Position.Left} className="dnode__handle" />
      <Handle type="source" id="r" position={Position.Right} className="dnode__handle" />
      <div className="dnode__name">
        {dot}
        {data.name}
      </div>
      <div className="dnode__role">
        {data.role || t('Senza ruolo')}
        {data.stack_size > 1 && <span className="dnode__stack" title={t('Stack di {n} switch', { n: data.stack_size })}>stack ×{data.stack_size}</span>}
      </div>
      {ip && <div className="dnode__ip">{ip}</div>}
      <Handle type="source" id="b" position={Position.Bottom} className="dnode__handle" />
    </div>
  )
}

export default memo(DeviceNode)
