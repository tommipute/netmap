import { useEffect, useRef, useState } from 'react'
import { api } from '../api'

const KIND = { device: 'Device', interface: 'Porta', ip: 'IP', endpoint: 'Collegato' }

/**
 * Ricerca nella mappa: nome o IP di management dei device in mappa (subito), poi MAC, IP e "dov'è collegato"
 * dal server (/search). Restano solo i risultati che portano a un device della mappa.
 * onPick({ deviceId, interfaceId, text }).
 */
export default function MapSearch({ nodes, onPick }) {
  const [q, setQ] = useState('')
  const [remote, setRemote] = useState([])
  const [open, setOpen] = useState(false)
  const boxRef = useRef(null)
  const term = q.trim().toLowerCase()

  useEffect(() => {
    if (term.length < 2) {
      setRemote([])
      return undefined
    }
    let alive = true
    const timer = setTimeout(async () => {
      try {
        const found = await api.get(`/search?q=${encodeURIComponent(term)}`)
        if (alive) setRemote(found)
      } catch {
        if (alive) setRemote([])
      }
    }, 250)
    return () => {
      alive = false
      clearTimeout(timer)
    }
  }, [term])

  useEffect(() => {
    const close = (e) => !boxRef.current?.contains(e.target) && setOpen(false)
    document.addEventListener('mousedown', close)
    return () => document.removeEventListener('mousedown', close)
  }, [])

  const inMap = new Map(nodes.map((n) => [n.id, n.name]))
  const local = term.length < 1 ? [] : nodes
    .filter((n) => n.name.toLowerCase().includes(term) || (n.primary_ip || '').startsWith(term))
    .map((n) => ({ key: `n${n.id}`, kind: 'device', label: n.name, detail: n.primary_ip?.split('/')[0], deviceId: n.id }))
  const seen = new Set(local.map((r) => r.deviceId))
  const others = remote
    .filter((r) => inMap.has(r.device_id) && !(r.type === 'device' && seen.has(r.device_id)))
    .map((r) => ({
      key: `${r.type}${r.id}`,
      kind: r.type,
      label: r.label,
      detail: r.type === 'device' ? inMap.get(r.device_id) : r.detail,
      deviceId: r.device_id,
      interfaceId: r.interface_id,
    }))
  const results = [...local, ...others].slice(0, 30)

  const pick = (r) => {
    setOpen(false)
    onPick({ deviceId: r.deviceId, interfaceId: r.interfaceId || null, text: r.kind === 'device' ? null : `${r.label} — ${r.detail}` })
  }

  return (
    <div className="combo map-search" ref={boxRef}>
      <input
        type="search"
        className="input input--sm"
        placeholder="Cerca nella mappa: nome, IP, MAC"
        aria-label="Cerca nella mappa"
        role="combobox"
        aria-expanded={open && results.length > 0}
        value={q}
        onChange={(e) => {
          setQ(e.target.value)
          setOpen(true)
        }}
        onFocus={() => setOpen(true)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' && results.length) pick(results[0])
          if (e.key === 'Escape') setOpen(false)
        }}
      />
      {open && term.length >= 1 && (
        <ul className="combo__list" role="listbox">
          {results.map((r) => (
            <li key={r.key}>
              <button type="button" role="option" aria-selected={false} className="combo__item" onClick={() => pick(r)}>
                <span className="map-search__kind">{KIND[r.kind]}</span>
                <span className={r.kind === 'device' ? '' : 'mono'}>{r.label}</span>
                {r.detail && <span className="muted"> · {r.detail}</span>}
              </button>
            </li>
          ))}
          {results.length === 0 && <li className="combo__more hint">{term.length < 2 ? 'Scrivi ancora…' : 'Niente in questa mappa'}</li>}
        </ul>
      )}
    </div>
  )
}
