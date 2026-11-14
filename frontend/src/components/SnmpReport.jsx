import { useState } from 'react'
import { api, qs } from '../api'
import { useAuth } from '../auth'
import { DEVICE_KINDS, formatDateTime } from '../options'
import { t, tn, tServer } from '../i18n'
import { Mono } from './Bits'
import ResourceForm from './ResourceForm'

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
  fdb_index_suffix: ['info', (n) => tn(n, '1 MAC con un numero in più dopo l\'indirizzo nell\'indice: letto lo stesso.', '{n} MAC con un numero in più dopo l\'indirizzo nell\'indice: letti lo stesso.')],
  fdb_address_column: ['info', (n) => tn(n, '1 MAC letto dalla colonna degli indirizzi: lo switch numera le righe invece di usare il MAC come indice.', '{n} MAC letti dalla colonna degli indirizzi: lo switch numera le righe invece di usare il MAC come indice.')],
  fdb_port_rule: ['info', (n) => tn(n, '1 riga della tabella MAC assegnata alla porta da una regola SNMP.', '{n} righe della tabella MAC assegnate alla porta da una regola SNMP.')],
  lldp_short_index: ['info', (n) => tn(n, '1 vicino LLDP con l\'indice accorciato: letto lo stesso.', '{n} vicini LLDP con l\'indice accorciato: letti lo stesso.')],
  lldp_local_ifindex: ['info', (n) => tn(n, '1 porta LLDP locale indicata con l\'ifIndex invece del nome: letta lo stesso.', '{n} porte LLDP locali indicate con l\'ifIndex invece del nome: lette lo stesso.')],
  lldp_port_rule: ['info', (n) => tn(n, '1 vicino LLDP collegato alla porta locale da una regola SNMP.', '{n} vicini LLDP collegati alla porta locale da una regola SNMP.')],
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
export function SnmpReportBody({ data, compact = false, report = null, onChanged, onRescan, rescanning = false }) {
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
        {data.sys_descr && (
          <div className="facts__wide"><dt>{t('Descrizione SNMP')}</dt><dd className="snmp-report__descr">{data.sys_descr}</dd></div>
        )}
      </dl>
      {report && <RulesChanged report={report} onRescan={onRescan} rescanning={rescanning} />}
      {!compact && <RuleHint data={data} onSaved={onChanged} />}
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

// Produttore che NetMap non conosce: nome provvisorio dal numero del sysObjectID
const PROVISIONAL_MANUFACTURER = /^Enterprise \d+$/

/** Cosa manca nella lettura e una regola SNMP può correggere */
function missingOf(data) {
  return [
    !data.model && t('modello'),
    (!data.manufacturer || PROVISIONAL_MANUFACTURER.test(data.manufacturer)) && t('produttore'),
    !data.kind && t('tipo di apparato'),
    data.notes?.fdb_unmapped && t('righe della tabella MAC'),
    data.notes?.neighbor_no_local_port && t('porta locale dei vicini'),
  ].filter(Boolean)
}

/** Solo amministratori: dice cosa si può correggere e apre una regola SNMP per questo apparato, con la prova pronta. */
function RuleHint({ data, onSaved }) {
  const { isAdmin } = useAuth()
  const [preset, setPreset] = useState(null)
  if (!isAdmin || !data.sys_object_id) return null
  const missing = missingOf(data)

  const open = async () => {
    let profileId = data.profile_id
    if (!profileId && data.profile) { // resoconti di prima della 1.4.1: solo il nome del profilo
      try {
        const page = await api.get(`/snmp-profiles${qs({ q: data.profile, limit: 50 })}`)
        profileId = page.items.find((p) => p.name === data.profile)?.id
      } catch { /* la prova resta da completare a mano */ }
    }
    setPreset({
      name: t('Apparati come {name}', { name: data.sys_name || data.host }),
      match_object_id: data.sys_object_id,
      rule_test: { host: data.host, profile_id: profileId },
    })
  }

  return (
    <div className="snmp-report__rule">
      <span>
        {missing.length
          ? t('Manca o non torna: {list}. Puoi correggerlo con una regola SNMP, che vale per tutti gli apparati di questo tipo.', { list: missing.join(', ') })
          : t('Qualcosa non torna? Puoi correggerlo con una regola SNMP, che vale per tutti gli apparati di questo tipo.')}
      </span>
      <button type="button" className="btn btn--sm" onClick={open}>{t('Crea una regola SNMP')}</button>
      {preset && <ResourceForm resourceKey="snmp-rules" preset={preset} onClose={() => setPreset(null)} onSaved={() => { setPreset(null); onSaved?.() }} />}
    </div>
  )
}

/** Regole SNMP nuove, cambiate o spente dopo l'ultima lettura: valgono dalla prossima (il pulsante la fa subito). */
function RulesChanged({ report, onRescan, rescanning }) {
  const now = report.rules_now || []
  const used = report.data.rules || []
  const readAt = new Date(report.read_at)
  const changed = now.length !== used.length || now.some((r, i) => r.name !== used[i] || new Date(r.updated_at) > readAt)
  if (!changed) return null
  const names = now.map((r) => r.name).join(', ')
  return (
    <div className="snmp-report__rule snmp-report__rule--pending">
      <span>
        {now.length
          ? tn(now.length, 'Le regole SNMP sono cambiate dopo questa lettura: ora vale {list}. Conta dalla prossima lettura.',
            'Le regole SNMP sono cambiate dopo questa lettura: ora valgono {list}. Contano dalla prossima lettura.', { list: names })
          : t('Le regole SNMP sono cambiate dopo questa lettura: ora non ne vale nessuna. Conta dalla prossima lettura.')}
      </span>
      {onRescan && (
        <button type="button" className="btn btn--sm btn--primary" onClick={onRescan} disabled={rescanning}>
          {rescanning ? t('Rilettura in corso…') : t('Rileggi ora')}
        </button>
      )}
    </div>
  )
}

/** Sezione della pagina del device, chiusa: si apre quando qualcosa non torna. */
export default function SnmpReport({ report, onChanged, onRescan, rescanning }) {
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
      <SnmpReportBody data={data} report={report} onChanged={onChanged} onRescan={onRescan} rescanning={rescanning} />
    </details>
  )
}
