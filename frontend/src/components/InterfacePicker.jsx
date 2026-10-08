import { useEffect, useState } from 'react'
import { api } from '../api'
import { useApi } from '../hooks'
import { RefSelect } from './RefSelect'
import { t } from '../i18n'

/**
 * Scelta di una porta in due passi: prima il device, poi la porta.
 * freeOnly: disabilita le porte già cablate (tranne quella del cavo che si sta modificando).
 */
export default function InterfacePicker({ value, onChange, fixedDeviceId, freeOnly = false, currentCableId = null, label }) {
  const [deviceId, setDeviceId] = useState(fixedDeviceId ?? '')

  useEffect(() => {
    if (fixedDeviceId) setDeviceId(fixedDeviceId)
  }, [fixedDeviceId])

  // In modifica conosco solo l'interfaccia: ricavo il device
  useEffect(() => {
    if (fixedDeviceId || !value || deviceId) return
    api.get(`/interfaces/${value}`).then((i) => setDeviceId(i.device_id)).catch(() => {})
  }, [value, fixedDeviceId, deviceId])

  const { data: ports, loading } = useApi(deviceId ? `/devices/${deviceId}/ports` : null)

  return (
    <div className="picker">
      <RefSelect
        resource="devices"
        value={deviceId}
        disabled={Boolean(fixedDeviceId)}
        emptyLabel={t('Scegli il device…')}
        ariaLabel={label ? `${label}: device` : t('Device')}
        onChange={(v) => {
          setDeviceId(v)
          onChange('')
        }}
      />
      <select
        className="input"
        value={value ?? ''}
        disabled={!deviceId || loading}
        aria-label={label ? `${label}: ${t('porta')}` : t('Porta')}
        onChange={(e) => onChange(e.target.value ? Number(e.target.value) : '')}
      >
        <option value="">{deviceId && ports && ports.length === 0 ? t('Il device non ha porte') : t('Scegli la porta…')}</option>
        {(ports || []).map((p) => {
          const takenBy = p.cable_id && p.cable_id !== currentCableId ? p.remote_device : null
          const unavailable = freeOnly && (!p.cableable || Boolean(takenBy))
          let note = ''
          if (freeOnly && !p.cableable) note = t(' (virtuale)')
          else if (takenBy) note = ` (${t('collegata a {where}', { where: `${takenBy} ${p.remote_interface}` })})`
          return (
            <option key={p.id} value={p.id} disabled={unavailable}>
              {p.name}
              {note}
            </option>
          )
        })}
      </select>
    </div>
  )
}
