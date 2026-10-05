import { useMemo, useState } from 'react'
import { api } from '../api'
import { invalidate } from '../hooks'
import { INTERFACE_MODES, INTERFACE_TYPES } from '../options'
import Modal from './Modal'
import { RefSelect } from './RefSelect'

const MAX_PORTS = 500

/** "Gi1/0/[1-48]" -> Gi1/0/1 … Gi1/0/48. Più intervalli si combinano: "[1-2]/0/[1-24]". */
export function expandPattern(pattern) {
  const text = pattern.trim()
  const match = text.match(/\[(\d+)-(\d+)\]/)
  if (!match) return text ? [text] : []
  const [whole, from, to] = match
  const start = Number(from)
  const end = Number(to)
  if (end < start) return []
  const result = []
  for (let n = start; n <= end && result.length <= MAX_PORTS; n++) {
    result.push(...expandPattern(text.replace(whole, String(n))))
  }
  return result
}

export default function BulkPortsDialog({ deviceId, onClose, onDone }) {
  const [pattern, setPattern] = useState('')
  const [type, setType] = useState('copper')
  const [speed, setSpeed] = useState('1000')
  const [mode, setMode] = useState('')
  const [vlan, setVlan] = useState('')
  const [progress, setProgress] = useState(null)
  const [report, setReport] = useState(null)

  const names = useMemo(() => expandPattern(pattern), [pattern])
  const tooMany = names.length > MAX_PORTS

  const submit = async (e) => {
    e.preventDefault()
    if (names.length === 0 || tooMany) return
    const failed = []
    for (let i = 0; i < names.length; i++) {
      setProgress(i + 1)
      try {
        await api.post('/interfaces', {
          device_id: deviceId,
          name: names[i],
          type,
          speed_mbps: speed ? Number(speed) : null,
          mode: mode || null,
          untagged_vlan_id: mode && vlan ? vlan : null,
        })
      } catch (err) {
        failed.push(`${names[i]}: ${err.message}`)
      }
    }
    invalidate()
    setProgress(null)
    if (failed.length === 0) onDone()
    else setReport({ created: names.length - failed.length, failed })
  }

  return (
    <Modal title="Aggiungi porte in blocco" onClose={report ? onDone : onClose}>
      {report ? (
        <div className="form">
          <p>
            Create {report.created} porte. Non create: {report.failed.length}.
          </p>
          <ul className="report">
            {report.failed.slice(0, 20).map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
          <div className="modal__footer">
            <button type="button" className="btn btn--primary" onClick={onDone}>Chiudi</button>
          </div>
        </div>
      ) : (
        <form className="form" onSubmit={submit} noValidate>
          <div className="form__grid">
            <div className="field field--wide">
              <label className="field__label" htmlFor="bulk-pattern">Nomi delle porte</label>
              <input id="bulk-pattern" className="input mono" value={pattern} placeholder="Gi1/0/[1-48]" onChange={(e) => setPattern(e.target.value)} />
              <span className="hint">
                {names.length === 0 && 'Usa [da-a] per un intervallo, ad esempio Gi1/0/[1-48] oppure [1-52].'}
                {names.length > 0 && !tooMany && `${names.length} porte: ${names[0]}${names.length > 1 ? ` … ${names[names.length - 1]}` : ''}`}
                {tooMany && `Troppe porte: massimo ${MAX_PORTS} alla volta.`}
              </span>
            </div>
            <div className="field">
              <label className="field__label" htmlFor="bulk-type">Tipo</label>
              <select id="bulk-type" className="input" value={type} onChange={(e) => setType(e.target.value)}>
                {INTERFACE_TYPES.map((o) => (
                  <option key={o.value} value={o.value}>{o.label}</option>
                ))}
              </select>
            </div>
            <div className="field">
              <label className="field__label" htmlFor="bulk-speed">Velocità (Mbps)</label>
              <input id="bulk-speed" type="number" className="input" value={speed} onChange={(e) => setSpeed(e.target.value)} />
            </div>
            <div className="field">
              <label className="field__label" htmlFor="bulk-mode">Modalità VLAN</label>
              <select id="bulk-mode" className="input" value={mode} onChange={(e) => setMode(e.target.value)}>
                <option value="">Nessuna (routed)</option>
                {INTERFACE_MODES.map((o) => (
                  <option key={o.value} value={o.value}>{o.label}</option>
                ))}
              </select>
            </div>
            {mode && (
              <div className="field">
                <label className="field__label" htmlFor="bulk-vlan">VLAN</label>
                <RefSelect id="bulk-vlan" resource="vlans" value={vlan} onChange={setVlan} />
              </div>
            )}
          </div>
          <div className="modal__footer">
            <button type="button" className="btn btn--ghost" onClick={onClose} disabled={progress !== null}>Annulla</button>
            <button type="submit" className="btn btn--primary" disabled={names.length === 0 || tooMany || progress !== null}>
              {progress !== null ? `Creo ${progress} di ${names.length}…` : `Crea ${names.length || ''} porte`.replace('  ', ' ')}
            </button>
          </div>
        </form>
      )}
    </Modal>
  )
}
