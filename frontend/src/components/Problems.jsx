// Problemi rilevati (services/problems.py): testi, priorità e tabella, per la pagina e per la scheda del device
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'
import { useAuth } from '../auth'
import { Mono } from './Bits'
import { IconButton } from './Icon'
import Modal from './Modal'
import { errDisableCause, formatDateTime, formatSince, formatSpeed, labelOf, PROBLEM_KINDS, SEVERITIES } from '../options'
import { t, tn } from '../i18n'

const SILENCE_DAYS = [
  { value: '1', label: t('1 giorno') },
  { value: '7', label: t('7 giorni') },
  { value: '30', label: t('30 giorni') },
  { value: '', label: t('Per sempre') },
]

export function SeverityBadge({ severity }) {
  const level = SEVERITIES.find((s) => s.value === severity)
  return <span className={`badge ${level?.badge || 'badge--muted'}`}>{level?.label || severity}</span>
}

/** Cosa succede e cosa fare, dal tipo e dai valori del problema */
function explain(p) {
  const v = p.values || {}
  const other = p.other_device_name ? `${p.other_device_name} ${p.other_interface_name || ''}`.trim() : ''
  switch (p.kind) {
    case 'loop':
      return [
        t('Le due porte vedono gli stessi {n} MAC e i due switch sono già collegati da un cavo documentato: c\'è un secondo percorso (hub, switch non gestito o cavo in più).', { n: v.macs }),
        t('Cerca cosa è collegato a quelle porte e toglilo. Con STP attivo una delle due dovrebbe risultare bloccata.'),
      ]
    case 'undocumented_link':
      return [
        t('La porta vede {n} MAC che sono anche sulle porte di accesso di {other}: in mezzo c\'è un collegamento che NetMap non conosce (hub, switch non gestito, cavo senza LLDP).', { n: v.macs, other: p.other_device_name }),
        t('Se è un collegamento voluto documenta il cavo, altrimenti controlla cosa c\'è collegato.'),
      ]
    case 'stp_storm':
      return [
        t('Il contatore dei cambi di topologia STP sale in fretta ({n} in totale): ogni cambio svuota le tabelle MAC e la rete rallenta.', { n: v.changes ?? '—' }),
        t('Di solito è un loop o una porta che va e viene: cercala, e attiva portfast (edge) sulle porte dei PC.'),
      ]
    case 'err_disabled':
      return [
        t('Lo switch ha spento la porta: {cause}.', { cause: errDisableCause(v.cause) }),
        v.cause === 'bpduGuard'
          ? t('Togli lo switch collegato, poi riattiva la porta (shutdown / no shutdown).')
          : t('Togli la causa, poi riattiva la porta (shutdown / no shutdown) o aspetta l\'errdisable recovery.'),
      ]
    case 'duplex_mismatch':
      return [
        t('Questa porta è in half duplex, {other} in full: il collegamento perde pacchetti e va lento.', { other }),
        t('Metti tutti e due i capi in autonegoziazione, oppure fissa velocità e duplex su entrambi.'),
      ]
    case 'native_vlan_mismatch':
      return [
        t('Da questa parte la VLAN non taggata è la {vlan}, su {other} è la {other_vlan}: il traffico non taggato finisce nella VLAN sbagliata.', { vlan: v.vlan, other_vlan: v.other_vlan, other }),
        t('Allinea la VLAN nativa (PVID) sui due capi.'),
      ]
    case 'duplicate_ip':
      return [
        t('{ip} è usato da più MAC: {macs}.', { ip: v.ip, macs: (v.macs || []).join(', ') }),
        t('Uno dei due ha l\'IP fisso uguale a un altro: cerca i MAC in "Dov\'è collegato?".'),
      ]
    case 'flapping':
      return [
        t('Ha cambiato stato {n} volte nelle ultime 24 ore.', { n: v.count }),
        t('Controlla cavo, presa, transceiver e il dispositivo collegato.'),
      ]
    case 'poe_fault':
      return [
        t('Lo switch segnala un guasto sull\'alimentazione PoE di questa porta.'),
        t('Prova un altro cavo o un altro dispositivo: può essere un corto o un dispositivo non compatibile.'),
      ]
    case 'poe_budget':
      return [
        t('{used} W usati su {budget} W ({pct}%).', { used: v.used, budget: v.budget, pct: Math.round((v.used / v.budget) * 100) }),
        t('Altri dispositivi PoE potrebbero non accendersi: spostane qualcuno su un altro switch.'),
      ]
    case 'errors_rising':
      return [
        t('Errori ricevuti {i}, inviati {o}: sono saliti nelle ultime 24 ore.', { i: (v.in ?? 0).toLocaleString(), o: (v.out ?? 0).toLocaleString() }),
        t('Di solito è il cavo o la presa: prova a cambiarli, e controlla il duplex.'),
      ]
    case 'half_duplex':
      return [
        t('Il collegamento non può trasmettere e ricevere insieme: va lento e fa collisioni.'),
        t('Controlla che l\'autonegoziazione sia attiva da tutte e due le parti.'),
      ]
    case 'speed_mismatch':
      return [
        t('{speed} da questa parte, {other_speed} su {other}: in mezzo c\'è probabilmente un altro apparato (switch non gestito, convertitore) o il cavo documentato non è giusto.', {
          speed: formatSpeed(v.speed), other_speed: formatSpeed(v.other_speed), other,
        }),
        t('Verifica il collegamento e la documentazione del cavo.'),
      ]
    case 'stp_blocked':
      return [
        t('STP blocca la porta perché c\'è un altro percorso verso la stessa rete, ma NetMap non conosce un cavo da qui verso un altro switch.'),
        t('Se è un collegamento di riserva documenta il cavo, altrimenti cerca cosa c\'è collegato (hub, switch non gestito, presa che torna in rete).'),
      ]
    case 'many_macs':
      return [
        t('Dietro la porta ci sono {n} MAC: probabilmente uno switch non gestito, un access point, un server con macchine virtuali o un uplink non documentato.', { n: v.macs }),
        t('Se è voluto va bene, altrimenti cerca lo switch non documentato.'),
      ]
    default:
      return [JSON.stringify(v), '']
  }
}

function When({ p }) {
  if (p.since) return <span title={formatDateTime(p.since)}>{formatSince(p.since)}</span>
  if (p.seen_at) return <span title={formatDateTime(p.seen_at)}>{t('visto {when}', { when: formatDateTime(p.seen_at) })}</span>
  return <span className="muted">—</span>
}

function Where({ p, deviceId }) {
  const device = (id, name) => (id === deviceId ? <strong>{name}</strong> : <Link to={`/devices/${id}`}>{name}</Link>)
  return (
    <>
      <div className="nowrap problems__end">{device(p.device_id, p.device_name)} {p.interface_name && <Mono>{p.interface_name}</Mono>}</div>
      {p.other_device_id && (
        <div className="nowrap problems__end">
          <span className="muted" aria-label={t('altro capo')}>↔ </span>
          {device(p.other_device_id, p.other_device_name)} {p.other_interface_name && <Mono>{p.other_interface_name}</Mono>}
        </div>
      )}
    </>
  )
}

/** Silenziato da chi, quando, fino a quando e perché */
function SilenceNote({ silence }) {
  return (
    <div className="hint problems__silence">
      {silence.until
        ? t('Silenziato da {who} il {when}, fino al {until}', { who: silence.created_by || '—', when: formatDateTime(silence.created_at, { exact: true }), until: formatDateTime(silence.until, { exact: true }) })
        : t('Silenziato da {who} il {when}, per sempre', { who: silence.created_by || '—', when: formatDateTime(silence.created_at, { exact: true }) })}
      {silence.note && <>: «{silence.note}»</>}
    </div>
  )
}

/** Finestra per silenziare un problema: per quanto e perché */
function SilenceDialog({ problem, onClose, onDone }) {
  const [days, setDays] = useState('7')
  const [note, setNote] = useState('')
  const [error, setError] = useState(null)
  const submit = async (e) => {
    e.preventDefault()
    try {
      await api.post('/problems/silences', { key: problem.key, note, days: days ? Number(days) : null })
      onDone()
    } catch (err) {
      setError(err.message)
    }
  }
  const where = `${problem.device_name}${problem.interface_name ? ` ${problem.interface_name}` : ''}`
  return (
    <Modal title={t('Silenzia il problema')} onClose={onClose}>
      <form className="form" onSubmit={submit}>
        <p>
          <strong>{labelOf(PROBLEM_KINDS, problem.kind)}</strong> · {where}
        </p>
        <p className="hint">{t('Il problema non conta più nei totali, nella Panoramica e nella scheda del device: resta in fondo alla pagina dei problemi, in grigio, e si può riattivare. Se sparisce e poi torna resta silenziato finché dura il silenzio.')}</p>
        <div className="form__grid">
          <label className="field">
            <span className="field__label">{t('Per quanto')}</span>
            <select className="input" value={days} onChange={(e) => setDays(e.target.value)}>
              {SILENCE_DAYS.map((d) => <option key={d.value} value={d.value}>{d.label}</option>)}
            </select>
          </label>
          <label className="field field--wide">
            <span className="field__label">{t('Perché (facoltativo)')}</span>
            <input className="input" value={note} maxLength={1000} onChange={(e) => setNote(e.target.value)}
              placeholder={t('es. collegamento di riserva voluto, switch da sostituire')} />
          </label>
        </div>
        {error && <p className="form__error" role="alert">{error}</p>}
        <div className="modal__footer">
          <button type="button" className="btn btn--ghost" onClick={onClose}>{t('Annulla')}</button>
          <button type="submit" className="btn btn--primary">{t('Silenzia')}</button>
        </div>
      </form>
    </Modal>
  )
}

/**
 * Tabella dei problemi; deviceId = scheda di quel device (il suo nome non è un link).
 * Con onChanged chi può modificare silenzia i problemi (e riattiva quelli silenziati: silenced).
 */
export function ProblemTable({ items, deviceId, onChanged, silenced = false }) {
  const { canEdit } = useAuth()
  const [silencing, setSilencing] = useState(null)
  const actions = canEdit && !!onChanged
  const restore = async (p) => {
    try {
      await api.del(`/problems/silences/${p.silenced.id}`)
      onChanged()
    } catch (err) {
      window.alert(err.message)
    }
  }
  return (
    <div className="table-wrap">
      <table className={`table table--dense problems${silenced ? ' problems--silenced' : ''}`}>
        <thead>
          <tr>
            <th>{t('Priorità')}</th>
            <th>{t('Problema')}</th>
            <th>{t('Dove')}</th>
            <th>{t('Quando')}</th>
            {actions && <th className="table__actions"><span className="sr-only">{t('Azioni')}</span></th>}
          </tr>
        </thead>
        <tbody>
          {items.map((p) => {
            const [detail, hint] = explain(p)
            return (
              <tr key={p.key || `${p.kind}-${p.device_id}-${p.interface_id}-${p.other_interface_id}`}>
                <td><SeverityBadge severity={p.severity} /></td>
                <td>
                  <div className="problems__title">{labelOf(PROBLEM_KINDS, p.kind)}</div>
                  <div>{detail}</div>
                  {hint && <div className="hint">{hint}</div>}
                  {p.kind === 'duplicate_ip' && <Link className="hint" to={`/where?q=${encodeURIComponent(p.values.ip)}`}>{t('Cerca l\'IP')}</Link>}
                  {p.silenced && <SilenceNote silence={p.silenced} />}
                </td>
                <td><Where p={p} deviceId={deviceId} /></td>
                <td className="nowrap"><When p={p} /></td>
                {actions && (
                  <td className="table__actions">
                    {p.silenced ? (
                      <IconButton icon="bell" label={t('Riattiva il problema')} small className="btn--ghost" onClick={() => restore(p)} />
                    ) : (
                      <IconButton icon="bellOff" label={t('Silenzia il problema')} small className="btn--ghost" onClick={() => setSilencing(p)} />
                    )}
                  </td>
                )}
              </tr>
            )
          })}
        </tbody>
      </table>
      {silencing && (
        <SilenceDialog problem={silencing} onClose={() => setSilencing(null)} onDone={() => { setSilencing(null); onChanged() }} />
      )}
    </div>
  )
}

/** Problemi silenziati, chiusi in fondo alla pagina */
export function SilencedProblems({ items, deviceId, onChanged }) {
  if (!items?.length) return null
  return (
    <details className="problems__silenced-box">
      <summary>{tn(items.length, '1 problema silenziato', '{n} problemi silenziati')}</summary>
      <ProblemTable items={items} deviceId={deviceId} onChanged={onChanged} silenced />
    </details>
  )
}
