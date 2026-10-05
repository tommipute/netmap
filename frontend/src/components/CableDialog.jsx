import { useState } from 'react'
import { api } from '../api'
import { invalidate } from '../hooks'
import { CABLE_STATUS, CABLE_TYPES } from '../options'
import InterfacePicker from './InterfacePicker'
import Modal from './Modal'

/** Crea un cavo tra due porte. I device possono essere già fissati (es. dalla mappa). */
export default function CableDialog({ aDeviceId, aInterfaceId, bDeviceId, onClose, onCreated }) {
  const [a, setA] = useState(aInterfaceId ?? '')
  const [b, setB] = useState('')
  const [type, setType] = useState('')
  const [status, setStatus] = useState('connected')
  const [label, setLabel] = useState('')
  const [error, setError] = useState(null)
  const [saving, setSaving] = useState(false)

  const submit = async (e) => {
    e.preventDefault()
    if (!a || !b) {
      setError('Scegli una porta per entrambi i lati.')
      return
    }
    setSaving(true)
    setError(null)
    try {
      const cable = await api.post('/cables', {
        a_interface_id: a,
        b_interface_id: b,
        type: type || null,
        status,
        label: label.trim() || null,
      })
      invalidate()
      onCreated(cable)
    } catch (err) {
      setError(err.message)
      setSaving(false)
    }
  }

  return (
    <Modal title="Nuovo collegamento" onClose={onClose}>
      <form className="form" onSubmit={submit} noValidate>
        <div className="form__grid">
          <div className="field field--wide">
            <span className="field__label">Lato A</span>
            <InterfacePicker fixedDeviceId={aDeviceId} value={a} onChange={setA} freeOnly label="Lato A" />
          </div>
          <div className="field field--wide">
            <span className="field__label">Lato B</span>
            <InterfacePicker fixedDeviceId={bDeviceId} value={b} onChange={setB} freeOnly label="Lato B" />
          </div>
          <div className="field">
            <label className="field__label" htmlFor="cable-type">Tipo cavo</label>
            <select id="cable-type" className="input" value={type} onChange={(e) => setType(e.target.value)}>
              <option value="">Non specificato</option>
              {CABLE_TYPES.map((o) => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </select>
          </div>
          <div className="field">
            <label className="field__label" htmlFor="cable-status">Stato</label>
            <select id="cable-status" className="input" value={status} onChange={(e) => setStatus(e.target.value)}>
              {CABLE_STATUS.map((o) => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </select>
          </div>
          <div className="field field--wide">
            <label className="field__label" htmlFor="cable-label">Etichetta</label>
            <input id="cable-label" className="input" value={label} placeholder="C-0142" onChange={(e) => setLabel(e.target.value)} />
          </div>
        </div>
        {error && <p className="form__error" role="alert">{error}</p>}
        <div className="modal__footer">
          <button type="button" className="btn btn--ghost" onClick={onClose}>Annulla</button>
          <button type="submit" className="btn btn--primary" disabled={saving}>
            {saving ? 'Salvataggio…' : 'Crea collegamento'}
          </button>
        </div>
      </form>
    </Modal>
  )
}
