import { Link } from 'react-router-dom'
import { CABLE_STATUS, CABLE_TYPES, DEVICE_STATUS, INTERFACE_MODES, INTERFACE_TYPES, IPAM_STATUS, IP_STATUS, SOURCES as DATA_SOURCES, formatDateTime } from '../options'
import { ROLES } from '../auth'
import { t, tData, tServer } from '../i18n'

export const OBJECT_TYPES = [
  { value: 'device', label: t('Device') },
  { value: 'interface', label: t('Porta') },
  { value: 'stack_member', label: t('Membro stack') },
  { value: 'cable', label: t('Cavo') },
  { value: 'ip', label: t('IP') },
  { value: 'vlan', label: t('VLAN') },
  { value: 'prefix', label: t('Subnet') },
  { value: 'vrf', label: t('VRF') },
  { value: 'site', label: t('Sede') },
  { value: 'location', label: t('Posizione') },
  { value: 'rack', label: t('Rack') },
  { value: 'device_type', label: t('Modello') },
  { value: 'device_role', label: t('Ruolo') },
  { value: 'manufacturer', label: t('Produttore') },
  { value: 'map', label: t('Mappa') },
  { value: 'snmp_profile', label: t('Profilo SNMP') },
  { value: 'discovery_job', label: t('Scansione') },
  { value: 'user', label: t('Utente') },
  { value: 'alert_channel', label: t('Canale di avviso') },
  { value: 'backup_target', label: t('Destinazione dei backup') },
  { value: 'directory', label: t('Active Directory') },
]
// Import da altri programmi: stesse etichette dell'origine dei dati (options.js)
const IMPORT_SOURCES = DATA_SOURCES.filter((o) => !['manual', 'snmp'].includes(o.value)).map(({ value, label }) => ({ value, label }))
export const SOURCES = [
  { value: 'utente', label: t('A mano') },
  { value: 'scansione', label: t('Scansione SNMP') },
  { value: 'import', label: t('Import CSV o Excel') },
  ...IMPORT_SOURCES,
  { value: 'directory', label: t('Accesso con Active Directory') },
  { value: 'sistema', label: t('Sistema') },
]
const ACTIONS = { create: [t('Creato'), 'ok'], update: [t('Modificato'), 'info'], delete: [t('Eliminato'), 'danger'] }
const typeLabel = (value) => OBJECT_TYPES.find((o) => o.value === value)?.label || value

// Valori fissi (stato, tipo, modo...) con le stesse parole dei menu
const VALUE_LABELS = Object.fromEntries(
  [DEVICE_STATUS, CABLE_STATUS, CABLE_TYPES, IPAM_STATUS, IP_STATUS, INTERFACE_TYPES, INTERFACE_MODES, ROLES]
    .flat()
    .map((o) => [o.value, o.label]),
)

function show(value) {
  if (value === null || value === undefined || value === '') return <span className="muted">{t('vuoto')}</span>
  if (value === true) return t('sì')
  if (value === false) return t('no')
  if (typeof value === 'object') return JSON.stringify(value)
  return VALUE_LABELS[value] ?? tData(String(value))
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
            <th>{t('Quando')}</th>
            <th>{t('Chi')}</th>
            {showObject && <th>{t('Cosa')}</th>}
            <th>{t('Modifiche')}</th>
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
                    {deviceLink ? <Link to={deviceLink}>{tData(e.label)}</Link> : <strong>{tData(e.label)}</strong>}
                  </td>
                )}
                <td>
                  {!showObject && (
                    <div>
                      <span className={`badge badge--${tone}`}>{action}</span>{' '}
                      <span className="muted">{typeLabel(e.object_type)}</span> <strong>{tData(e.label)}</strong>
                    </div>
                  )}
                  {e.changes.length === 0 ? (
                    showObject && <span className="muted">—</span>
                  ) : (
                    <ul className="history__changes">
                      {e.changes.map(([field, before, after]) => (
                        <li key={field}>
                          <span className="muted">{tServer(field)}:</span> {show(before)} <span aria-label={t('diventa')}>→</span> <strong>{show(after)}</strong>
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
