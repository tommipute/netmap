import { DEVICE_KINDS, formatDateTime } from '../options'
import { t, tn, tServer } from '../i18n'
import { Mono } from './Bits'

// Tabelle lette, nell'ordine della scansione: chiave in counts, nome, MIB da cui arrivano
const ROWS = [
  ['interfaces', () => t('Porte'), 'IF-MIB'],
  ['ips', () => t('Indirizzi IP'), 'IP-MIB'],
  ['members', () => t('Membri dello stack'), 'ENTITY-MIB'],
  ['lldp', () => t('Vicini LLDP'), 'LLDP-MIB'],
  ['cdp', () => t('Vicini CDP'), 'CISCO-CDP-MIB'],
  ['vlans', () => t('VLAN'), 'Q-BRIDGE-MIB, CISCO-VTP-MIB'],
  ['port_vlans', () => t('Porte con la VLAN'), 'Q-BRIDGE-MIB, CISCO-VLAN-MEMBERSHIP-MIB'],
  ['fdb', () => t('Tabella MAC'), null],
  ['arp', () => t('Tabella ARP'), 'IP-MIB'],
]

const kindLabel = (key) => DEVICE_KINDS.find((k) => k.value === key)?.label || key

const FDB_SOURCES = { qbridge: 'Q-BRIDGE-MIB', bridge: 'BRIDGE-MIB' }

const MODEL_SOURCES = {
  entity: () => t('dalla ENTITY-MIB'),
  sysdescr: () => t('dalla descrizione SNMP'),
  chassis: () => t('dalla descrizione dello chassis'),
  rule: () => t('da una regola SNMP'),
}

// Adattamenti alle stranezze dello switch (info) e righe scartate (warn); n = righe interessate
const NOTES = {
  bridge_port_ifindex: ['info', () => t("Lo switch non ha la tabella che collega le porte del bridge alle porte (dot1dBasePortIfIndex): NetMap usa il numero della porta come ifIndex, come per gli altri switch che la omettono.")],
  mac_length_prefix: ['info', (n) => tn(n, '1 MAC scritto con la lunghezza davanti all\'indirizzo: letto lo stesso.', '{n} MAC scritti con la lunghezza davanti all\'indirizzo: letti lo stesso.')],
  fdb_on_lag: ['info', (n) => tn(n, '1 MAC imparato su un aggregato (LAG): assegnato all\'aggregato.', '{n} MAC imparati su un aggregato (LAG): assegnati all\'aggregato.')],
  cisco_vlan_fdb: ['info', (n) => tn(n, 'Tabella MAC letta VLAN per VLAN (1 VLAN).', 'Tabella MAC letta VLAN per VLAN ({n} VLAN).')],
  renamed_ports: ['info', (n) => tn(n, '1 porta ha lo stesso nome di un\'altra: ha preso la sua descrizione SNMP o il nome con il numero.', '{n} porte hanno lo stesso nome di un\'altra: hanno preso la loro descrizione SNMP o il nome con il numero.')],
  fdb_unmapped: ['warn', (n) => tn(n, '1 riga della tabella MAC indica una porta che lo switch non elenca: scartata.', '{n} righe della tabella MAC indicano una porta che lo switch non elenca: scartate.')],
  fdb_bad_index: ['warn', (n) => tn(n, '1 riga della tabella MAC non ha un MAC valido: scartata.', '{n} righe della tabella MAC non hanno un MAC valido: scartate.')],
  ports_ignored: ['info', (n) => tn(n, '1 porta ignorata da una regola SNMP.', '{n} porte ignorate da una regola SNMP.')],
  neighbor_no_local_port: ['warn', (n) => tn(n, '1 vicino LLDP/CDP è su una porta che NetMap non riconosce: non diventa un cavo.', '{n} vicini LLDP/CDP sono su una porta che NetMap non riconosce: non diventano cavi.')],
}

/**
 * Cosa ha letto la scansione da un apparato, tabella per tabella, con gli adattamenti e cosa non si è letto.
 * `compact` (prova indirizzi, dove i problemi sono già scritti sopra): senza la colonna delle MIB e senza i problemi.
 */
export function SnmpReportBody({ data, compact = false }) {
  const notes = Object.entries(data.notes || {}).filter(([key]) => NOTES[key])
  const model = MODEL_SOURCES[data.model_source]
  return (
    <div className="snmp-report">
      <dl className="facts snmp-report__facts">
        <div>
          <dt>{t('Modello')}</dt>
          <dd>
            {data.model ? <><Mono>{data.model}</Mono>{model && <span className="muted"> {model()}</span>}</> : <span className="muted">{t('non trovato')}</span>}
          </dd>
        </div>
        <div><dt>{t('Numero di serie')}</dt><dd>{data.serial ? <Mono>{data.serial}</Mono> : <span className="muted">{t('non trovato')}</span>}</dd></div>
        <div>
          <dt>{t('Produttore (sysObjectID)')}</dt>
          <dd>{data.manufacturer || <span className="muted">—</span>} {data.sys_object_id && <Mono>{data.sys_object_id}</Mono>}</dd>
        </div>
        {data.kind && (
          <div>
            <dt>{t('Tipo di apparato')}</dt>
            <dd>{kindLabel(data.kind)} {data.kind_reason && <span className="muted">({tServer(data.kind_reason)})</span>}</dd>
          </div>
        )}
        {data.rules?.length > 0 && (
          <div><dt>{t('Regole SNMP')}</dt><dd>{data.rules.join(', ')}</dd></div>
        )}
      </dl>
      <table className="table table--dense snmp-report__table">
        <thead>
          <tr><th>{t('Dati')}</th><th>{t('Righe lette')}</th>{!compact && <th>{t('Da')}</th>}</tr>
        </thead>
        <tbody>
          {ROWS.map(([key, label, mib]) => {
            const n = data.counts?.[key] ?? 0
            const source = key === 'fdb' ? FDB_SOURCES[data.fdb_source] : mib
            return (
              <tr key={key}>
                <td>{label()}</td>
                <td>{n > 0 ? n : <span className="muted">{t('niente')}</span>}</td>
                {!compact && <td className="muted">{source || '—'}</td>}
              </tr>
            )
          })}
        </tbody>
      </table>
      {notes.length > 0 && (
        <ul className="snmp-report__notes">
          {notes.map(([key, n]) => {
            const [tone, text] = NOTES[key]
            return <li key={key} className={`snmp-report__note snmp-report__note--${tone}`}>{text(n)}</li>
          })}
        </ul>
      )}
      {!compact && data.problems?.length > 0 && (
        <ul className="probe__problems">
          {data.problems.map((p) => <li key={p}>{t('Non letto')}: {tServer(p)}</li>)}
        </ul>
      )}
      <p className="hint">{t('"Niente" vuol dire che lo switch non ha risposto con dati per quella tabella: può non averla, averla vuota o non darla con questo profilo SNMP.')}</p>
    </div>
  )
}

/** Sezione della pagina del device, chiusa: si apre quando qualcosa non torna. */
export default function SnmpReport({ report }) {
  if (!report) return null
  const { data } = report
  return (
    <details className="section disclosure no-print">
      <summary className="section__head">
        <h2>
          {t('Cosa ho letto via SNMP')}
          <span className="section__count">
            {t('{date} da {host}, profilo {profile}', { date: formatDateTime(report.read_at), host: data.host, profile: data.profile || '—' })}
          </span>
        </h2>
      </summary>
      <SnmpReportBody data={data} />
    </details>
  )
}
