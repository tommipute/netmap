import { Link } from 'react-router-dom'
import { CABLE_STATUS, CABLE_TYPES, DEVICE_STATUS, INTERFACE_MODES, INTERFACE_TYPES, IPAM_STATUS, IP_STATUS, formatDateTime } from '../options'
import { ROLES } from '../auth'

export const OBJECT_TYPES = [
  { value: 'device', label: 'Device' },
  { value: 'interface', label: 'Porta' },
  { value: 'cable', label: 'Cavo' },
  { value: 'ip', label: 'IP' },
  { value: 'vlan', label: 'VLAN' },
  { value: 'prefix', label: 'Subnet' },
  { value: 'vrf', label: 'VRF' },
  { value: 'site', label: 'Sede' },
  { value: 'location', label: 'Posizione' },
  { value: 'rack', label: 'Rack' },
  { value: 'device_type', label: 'Modello' },
  { value: 'device_role', label: 'Ruolo' },
  { value: 'manufacturer', label: 'Produttore' },
  { value: 'map', label: 'Mappa' },
  { value: 'snmp_profile', label: 'Profilo SNMP' },
  { value: 'discovery_job', label: 'Scansione' },
  { value: 'user', label: 'Utente' },
]
export const SOURCES = [
  { value: 'utente', label: 'A mano' },
  { value: 'scansione', label: 'Scansione SNMP' },
  { value: 'import', label: 'Import CSV' },
  { value: 'sistema', label: 'Sistema' },
]
const ACTIONS = { create: ['Creato', 'ok'], update: ['Modificato', 'info'], delete: ['Eliminato', 'danger'] }
const typeLabel = (value) => OBJECT_TYPES.find((t) => t.value === value)?.label || value

// Valori fissi (stato, tipo, modo...) con le stesse parole dei menu
const VALUE_LABELS = Object.fromEntries(
  [DEVICE_STATUS, CABLE_STATUS, CABLE_TYPES, IPAM_STATUS, IP_STATUS, INTERFACE_TYPES, INTERFACE_MODES, ROLES]
    .flat()
    .map((o) => [o.value, o.label]),
)

function show(value) {
  if (value === null || value === undefined || value === '') return <span className="muted">vuoto</span>
  if (value === true) return 'sì'
  if (value === false) return 'no'
  if (typeof value === 'object') return JSON.stringify(value)
  return VALUE_LABELS[value] ?? String(value)
}

/** Chi l'ha fatto: l'utente, e se è passata dalla scansione o dall'import anche quello. */
function Who({ entry }) {
  const source = SOURCES.find((s) => s.value === entry.source)?.label
  if (!entry.username) return <span className="muted">{source}</span>
  return (
    <>
      {entry.username}
      {entry.source !== 'utente' && <div className="hint">{source}</div>}
    </>
  )
}

/** Righe dello storico (dalla più recente): quando, chi, cosa e i campi cambiati prima → dopo. */
export default function HistoryList({ entries, showObject = true }) {
  return (
    <div className="table-wrap">
      <table className="table table--dense history">
        <thead>
          <tr>
            <th>Quando</th>
            <th>Chi</th>
            {showObject && <th>Cosa</th>}
            <th>Modifiche</th>
          </tr>
        </thead>
        <tbody>
          {entries.map((e) => {
            const [action, tone] = ACTIONS[e.action] || [e.action, 'muted']
            const deviceLink = e.object_type === 'device' && e.action !== 'delete' ? `/devices/${e.object_id}` : null
            return (
              <tr key={e.id}>
                <td className="history__when">{formatDateTime(e.at)}</td>
                <td><Who entry={e} /></td>
                {showObject && (
                  <td>
                    <span className={`badge badge--${tone}`}>{action}</span>{' '}
                    <span className="muted">{typeLabel(e.object_type)}</span>{' '}
                    {deviceLink ? <Link to={deviceLink}>{e.label}</Link> : <strong>{e.label}</strong>}
                  </td>
                )}
                <td>
                  {!showObject && (
                    <div>
                      <span className={`badge badge--${tone}`}>{action}</span>{' '}
                      <span className="muted">{typeLabel(e.object_type)}</span> <strong>{e.label}</strong>
                    </div>
                  )}
                  {e.changes.length === 0 ? (
                    showObject && <span className="muted">—</span>
                  ) : (
                    <ul className="history__changes">
                      {e.changes.map(([field, before, after]) => (
                        <li key={field}>
                          <span className="muted">{field}:</span> {show(before)} <span aria-label="diventa">→</span> <strong>{show(after)}</strong>
                        </li>
                      ))}
                    </ul>
                  )}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
