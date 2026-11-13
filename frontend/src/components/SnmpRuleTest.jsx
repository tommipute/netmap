import { useState } from 'react'
import { api } from '../api'
import { DEVICE_KINDS } from '../options'
import { t, tn, tServer } from '../i18n'
import { ErrorBox, Mono } from './Bits'
import { RefSelect } from './RefSelect'

const kindLabel = (key) => DEVICE_KINDS.find((k) => k.value === key)?.label || key

// Righe del confronto: cosa può cambiare una regola, come lo scrive il resoconto
const ROWS = [
  ['model', () => t('Modello'), (r) => r.model],
  ['serial', () => t('Numero di serie'), (r) => r.serial],
  ['manufacturer', () => t('Produttore'), (r) => r.manufacturer],
  ['kind', () => t('Tipo di apparato'), (r) => r.kind && `${kindLabel(r.kind)} (${tServer(r.kind_reason)})`],
  ['interfaces', () => t('Porte'), (r) => r.counts?.interfaces],
  ['fdb', () => t('Tabella MAC'), (r) => r.counts?.fdb],
  ['lldp', () => t('Vicini LLDP'), (r) => r.counts?.lldp],
  ['rules', () => t('Regole SNMP'), (r) => r.rules?.join(', ') || null],
]
const MAX_PORTS = 20

/** Regola SNMP com'è nel modulo -> corpo della prova (stessi campi della creazione) */
function draftOf(values) {
  const rule = {}
  for (const [key, value] of Object.entries(values)) {
    if (key === 'rule_test') continue
    if (key === 'ignore_if_types') rule[key] = (value || []).map(Number).filter(Number.isFinite)
    else if (typeof value === 'string') rule[key] = value.trim() || null
    else rule[key] = value
  }
  rule.name = rule.name || t('Regola in prova')
  return rule
}

/** Campo del modulo delle regole SNMP: prova la regola com'è (anche non salvata) su un indirizzo, prima e dopo. */
export default function SnmpRuleTest({ values, item }) {
  const [host, setHost] = useState('')
  const [profile, setProfile] = useState('')
  const [result, setResult] = useState(null)
  const [running, setRunning] = useState(false)
  const [error, setError] = useState(null)

  const run = async () => {
    setRunning(true)
    setError(null)
    setResult(null)
    try {
      setResult(await api.post('/snmp-rules/test', {
        host, profile_ids: [Number(profile)], rule_id: item?.id ?? null, rule: draftOf(values),
      }))
    } catch (err) {
      setError(err)
    } finally {
      setRunning(false)
    }
  }

  return (
    <div className="rule-test">
      <div className="rule-test__inputs">
        <input className="input mono" value={host} onChange={(e) => setHost(e.target.value)} placeholder={t('IP di un apparato')}
          aria-label={t('IP di un apparato')} onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); if (host && profile) run() } }} />
        <RefSelect resource="snmp-profiles" value={profile} onChange={setProfile} emptyLabel={t('Profilo SNMP…')} ariaLabel={t('Profilo SNMP')} />
        <button type="button" className="btn" onClick={run} disabled={running || !host.trim() || !profile}>
          {running ? t('Prova in corso…') : t('Prova')}
        </button>
      </div>
      <span className="hint">{t('Legge l\'apparato e mostra cosa cambia con la regola com\'è adesso nel modulo, senza salvare niente. "Prima" conta le altre regole attive.')}</span>
      <ErrorBox error={error} />
      {result && <RuleTestResult result={result} />}
    </div>
  )
}

function RuleTestResult({ result }) {
  if (!result.before) {
    return (
      <div className="rule-test__result">
        {result.error && <div>{t('Lettura SNMP fallita: {error}', { error: result.error })}</div>}
        <ul className="probe__attempts">
          {result.attempts.map((a) => <li key={a.profile}><strong>{a.profile}</strong>: {tServer(a.error)}</li>)}
        </ul>
      </div>
    )
  }
  const { before, after, ports } = result
  return (
    <div className="rule-test__result">
      {!result.matches && (
        <p className="snmp-report__note snmp-report__note--warn">
          {t('La regola non vale per questo apparato: controlla l\'inizio del sysObjectID e la descrizione.')}
        </p>
      )}
      <dl className="facts">
        <div><dt>{t('sysObjectID')}</dt><dd><Mono>{before.sys_object_id || '—'}</Mono></dd></div>
        <div><dt>{t('Descrizione SNMP')}</dt><dd className="rule-test__descr">{before.sys_descr || '—'}</dd></div>
      </dl>
      <table className="table table--dense">
        <thead><tr><th>{t('Dati')}</th><th>{t('Prima')}</th><th>{t('Dopo')}</th></tr></thead>
        <tbody>
          {ROWS.map(([key, label, value]) => {
            const a = value(before) ?? null
            const b = value(after) ?? null
            return (
              <tr key={key} className={a !== b ? 'rule-test__changed' : undefined}>
                <td>{label()}</td>
                <td>{a ?? <span className="muted">—</span>}</td>
                <td>{b ?? <span className="muted">—</span>}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
      {ports.length > 0 && (
        <>
          <p className="field__label">{tn(ports.length, '1 porta cambia', '{n} porte cambiano')}</p>
          <ul className="rule-test__ports">
            {ports.slice(0, MAX_PORTS).map((p) => (
              <li key={p.if_index}>
                <Mono>{p.before}</Mono> → {p.after ? <Mono>{p.after}</Mono> : <span className="muted">{t('ignorata')}</span>}
              </li>
            ))}
            {ports.length > MAX_PORTS && <li className="muted">{t('e altre {n}', { n: ports.length - MAX_PORTS })}</li>}
          </ul>
        </>
      )}
    </div>
  )
}
