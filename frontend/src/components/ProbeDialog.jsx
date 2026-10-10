import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'
import { LOCALE, t, tn, tServer } from '../i18n'
import { targetError, targetsSummary } from '../targets'
import { ErrorBox, Mono } from './Bits'
import ChipInput from './ChipInput'
import Modal from './Modal'
import { RefMulti } from './RefSelect'

export const PROBE_MAX_HOSTS = 256 // come MAX_HOSTS in backend/app/discovery/probe.py

// Esito di un indirizzo: letto, risponde con un errore (v3), solo ping, niente
function outcome(r) {
  if (r.found) return 'ok'
  if (r.error || r.attempts.some((a) => a.answered)) return 'error'
  return r.ping_ms != null ? 'ping' : 'none'
}
const OUTCOMES = {
  ok: { tone: 'ok', label: () => t('Letto') },
  error: { tone: 'danger', label: () => t('Errore') },
  ping: { tone: 'warn', label: () => t('Solo ping') },
  none: { tone: 'muted', label: () => t('Nessuna risposta') },
}

function Found({ f }) {
  const model = [f.manufacturer, f.model].filter(Boolean).join(' ')
  const counts = [
    tn(f.interfaces, '1 porta', '{n} porte'),
    tn(f.ips, '1 IP', '{n} IP'),
    tn(f.neighbors, '1 vicino', '{n} vicini'),
    tn(f.vlans, '1 VLAN', '{n} VLAN'),
    f.members > 1 && tn(f.members, '1 membro dello stack', '{n} membri dello stack'),
    f.fdb > 0 && tn(f.fdb, '1 MAC', '{n} MAC'),
  ].filter(Boolean)
  return (
    <>
      <div>
        <strong>{f.sys_name || t('(senza sysName)')}</strong>
        {model && <> · {model}{!f.model_known && <span className="muted"> ({t('modello nuovo')})</span>}</>}
        {f.kind && <> · {tServer(f.kind)}</>}
      </div>
      <div className="muted">
        {t('Profilo {name}', { name: f.profile })} · {counts.join(', ')} ·{' '}
        {f.device_id ? <>{t('in NetMap:')} <Link to={`/devices/${f.device_id}`}>{f.device_name}</Link></> : t('device nuovo')}
      </div>
      {f.problems.length > 0 && (
        <ul className="probe__problems">
          {f.problems.map((p) => <li key={p}>{t('Non letto')}: {tServer(p)}</li>)}
        </ul>
      )}
    </>
  )
}

function Attempts({ r, kind }) {
  return (
    <>
      {r.error && <div>{t('Lettura SNMP fallita: {error}', { error: r.error })}</div>}
      <ul className="probe__attempts">
        {r.attempts.map((a) => <li key={a.profile}><strong>{a.profile}</strong>: {tServer(a.error)}</li>)}
      </ul>
      {kind === 'ping' && (
        <div className="muted">{t("Risponde al ping: c'è un apparato, ma non accetta questi profili. Controlla community o utente, che SNMP sia attivo e che l'ACL ammetta l'indirizzo di NetMap.")}</div>
      )}
    </>
  )
}

/** Prova di pochi indirizzi senza salvare niente: ping, esito di ogni profilo, cosa si leggerebbe. */
export default function ProbeDialog({ onClose, targets: initialTargets = [], profileIds = [] }) {
  const [targets, setTargets] = useState(initialTargets)
  const [profiles, setProfiles] = useState(profileIds)
  const [results, setResults] = useState(null)
  const [running, setRunning] = useState(false)
  const [error, setError] = useState(null)
  const [showSilent, setShowSilent] = useState(false)

  const summary = targetsSummary(targets, PROBE_MAX_HOSTS)
  const invalid = targets.some((x) => targetError(x)) || summary?.error

  const run = async (e) => {
    e.preventDefault()
    setRunning(true)
    setError(null)
    try {
      setResults(await api.post('/discovery/probe', { targets, profile_ids: profiles }))
    } catch (err) {
      setError(err)
    } finally {
      setRunning(false)
    }
  }

  const kinds = (results || []).map((r) => [r, outcome(r)])
  const count = (k) => kinds.filter(([, kind]) => kind === k).length
  const shown = kinds.filter(([, kind]) => showSilent || kind !== 'none')

  return (
    <Modal title={t('Prova indirizzi')} wide onClose={onClose}>
      <form className="form" onSubmit={run} noValidate>
        <p className="hint">
          {t('Interroga subito pochi indirizzi (al massimo {max}) con i profili scelti e dice cosa succede su ognuno, senza salvare niente: serve a sistemare community, utenti e ACL prima della scansione.', { max: PROBE_MAX_HOSTS })}
        </p>
        <div className="form__grid">
          <div className="field field--wide">
            <label className="field__label" htmlFor="probe-targets">{t('Indirizzi')}</label>
            <ChipInput id="probe-targets" value={targets} onChange={setTargets} placeholder={t('10.0.99.1, 10.0.99.10-20, 10.0.99.0/28')}
              validate={targetError} summary={() => summary} label={t('Indirizzi')} />
          </div>
          <div className="field field--wide">
            <span className="field__label">{t('Profili SNMP da provare')}</span>
            <RefMulti resource="snmp-profiles" value={profiles} onChange={setProfiles} ordered />
          </div>
        </div>
        <ErrorBox error={error} />
        <div className="modal__footer">
          <button type="button" className="btn btn--ghost" onClick={onClose}>{t('Chiudi')}</button>
          <button type="submit" className="btn btn--primary" disabled={running || !targets.length || !profiles.length || invalid}>
            {running ? t('Prova in corso…') : t('Prova')}
          </button>
        </div>
      </form>

      {results && (
        <div className="probe">
          <p>
            {[
              tn(count('ok'), '1 letto', '{n} letti'),
              count('error') && tn(count('error'), '1 risponde con un errore', '{n} rispondono con un errore'),
              count('ping') && tn(count('ping'), '1 risponde solo al ping', '{n} rispondono solo al ping'),
              count('none') && tn(count('none'), '1 non risponde', '{n} non rispondono'),
            ].filter(Boolean).join(' · ')}
          </p>
          {count('none') > 0 && (
            <label className="check">
              <input type="checkbox" checked={showSilent} onChange={(e) => setShowSilent(e.target.checked)} />
              {t('Mostra anche gli indirizzi che non rispondono')}
            </label>
          )}
          {shown.length > 0 && (
            <div className="table-wrap">
              <table className="table table--dense">
                <thead>
                  <tr>
                    <th>{t('Indirizzo')}</th>
                    <th>{t('Ping')}</th>
                    <th>{t('Esito')}</th>
                    <th>{t('Dettagli')}</th>
                  </tr>
                </thead>
                <tbody>
                  {shown.map(([r, kind]) => (
                    <tr key={r.host}>
                      <td><Mono>{r.host}</Mono></td>
                      <td className="probe__ping">{r.ping_ms != null ? `${r.ping_ms.toLocaleString(LOCALE)} ms` : '—'}</td>
                      <td><span className={`badge badge--${OUTCOMES[kind].tone}`}>{OUTCOMES[kind].label()}</span></td>
                      <td>{r.found ? <Found f={r.found} /> : <Attempts r={r} kind={kind} />}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </Modal>
  )
}
