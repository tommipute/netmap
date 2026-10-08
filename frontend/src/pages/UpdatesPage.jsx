import { useEffect, useState } from 'react'
import { api } from '../api'
import { ErrorBox, Loading } from '../components/Bits'
import Modal from '../components/Modal'
import { useApi } from '../hooks'
import { formatDateTime, formatSince } from '../options'
import { t, tServer } from '../i18n'

const INTERVALS = [
  { value: 15, label: t('Ogni 15 minuti') },
  { value: 30, label: t('Ogni 30 minuti') },
  { value: 60, label: t('Ogni ora') },
  { value: 180, label: t('Ogni 3 ore') },
  { value: 360, label: t('Ogni 6 ore') },
  { value: 720, label: t('Ogni 12 ore') },
  { value: 1440, label: t('Una volta al giorno') },
]
const OUTCOMES = {
  success: { label: t('Completato'), tone: 'ok' },
  error: { label: t('Errore'), tone: 'danger' },
  rolled_back: { label: t('Rollback eseguito'), tone: 'warn' },
}
const BUSY = { checking: t('Controllo in corso'), updating: t('Aggiornamento in corso'), rolling_back: t('Rollback in corso') }

// I messaggi dello script sono frasi italiane: le traduco una per una
const tMessage = (text) => (text || '').split(/(?<=\.)\s+/).map((part) => tServer(part)).join(' ')

function Version({ info }) {
  if (!info?.commit) return <span className="muted">—</span>
  return (
    <>
      <strong>{info.version || info.short}</strong> <code title={info.commit}>{info.short}</code>
      {info.tag && <span className="tag">{info.tag}</span>}
      <span className="hint update-version__meta">
        {info.date && formatDateTime(info.date)}{info.subject && ` · ${info.subject}`}
      </span>
    </>
  )
}

/** Stato "live": in corso, in attesa (richiesta inviata) oppure l'esito dell'ultimo aggiornamento. */
function LiveState({ status, request }) {
  const activity = status?.activity
  if (activity && BUSY[activity]) {
    return (
      <div className="update-live">
        <span className="badge badge--info"><span className="update-spinner" aria-hidden="true" />{BUSY[activity]}</span>
        <span>{tMessage(status.activity_message)}</span>
        {status.activity_since && <span className="hint">{formatSince(status.activity_since)}</span>}
      </div>
    )
  }
  if (request) {
    return (
      <div className="update-live">
        <span className="badge badge--muted">{t('In attesa')}</span>
        <span>{request.action === 'update' ? t('Aggiornamento richiesto') : t('Controllo richiesto')}: {t('lo script lo esegue entro un minuto.')}</span>
      </div>
    )
  }
  const last = status?.last_result
  const outcome = last && OUTCOMES[last.outcome]
  if (!outcome) {
    return <div className="update-live"><span className="badge badge--muted">{t('In attesa')}</span><span className="muted">{t('Nessun aggiornamento eseguito finora.')}</span></div>
  }
  return (
    <div className="update-live">
      <span className={`badge badge--${outcome.tone}`}>{outcome.label}</span>
      <span>{tMessage(last.message)}</span>
      <span className="hint">{formatDateTime(last.at)}</span>
    </div>
  )
}

/** Avvisi quando lo script non c'è, non è mai partito o tace da troppo. */
function ScriptWarning({ data }) {
  const steps = (
    <p className="hint">{t('Sul server, nella cartella di NetMap: sudo updater/install.sh, poi docker compose up -d. Istruzioni complete nel README, sezione «Aggiornamenti automatici».')}</p>
  )
  if (data.script === 'not_mounted') {
    return (
      <div className="notice notice--warn">
        <strong>{t("La cartella condivisa con l'updater non è montata.")}</strong>{' '}
        {t("L'app non può vedere né chiedere aggiornamenti: il container api deve montare updater-data in /updater-data (docker-compose.yml aggiornato).")}
        {steps}
      </div>
    )
  }
  if (data.script === 'never_ran') {
    return (
      <div className="notice notice--warn">
        <strong>{t("Lo script di aggiornamento non è mai partito.")}</strong>{' '}
        {t('La cartella è montata ma lo script non ha ancora scritto lo stato: probabilmente non è installato sul server.')}
        {steps}
      </div>
    )
  }
  if (data.script === 'silent' || data.script === 'stuck') {
    return (
      <div className="notice notice--warn">
        <strong>
          {data.script === 'stuck'
            ? t("Lo script sembra bloccato a metà di un'operazione.")
            : t('Lo script tace da {n} minuti (dovrebbe girare ogni minuto).', { n: data.silent_minutes ?? '?' })}
        </strong>{' '}
        {t('Sul server controlla il timer: systemctl status netmap-updater.timer e journalctl -u netmap-updater.')}
      </div>
    )
  }
  return null
}

function SettingsForm({ settings, disabled, onSaved }) {
  const [form, setForm] = useState(settings)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)
  const [saved, setSaved] = useState(false)
  useEffect(() => setForm(settings), [settings])
  const set = (name, value) => { setForm((prev) => ({ ...prev, [name]: value })); setSaved(false) }
  const changed = JSON.stringify(form) !== JSON.stringify(settings)
  const intervals = INTERVALS.some((o) => o.value === form.check_interval_minutes)
    ? INTERVALS
    : [...INTERVALS, { value: form.check_interval_minutes, label: t('Ogni {n} minuti', { n: form.check_interval_minutes }) }]

  const submit = async (e) => {
    e.preventDefault()
    setSaving(true)
    setError(null)
    try {
      await api.put('/updates/settings', form)
      setSaved(true)
      onSaved()
    } catch (err) {
      setError(err)
    } finally {
      setSaving(false)
    }
  }

  return (
    <form className="form" onSubmit={submit}>
      <div className="form__grid">
        <div className="field field--wide">
          <label className="check">
            <input type="checkbox" checked={form.auto_update} disabled={disabled} onChange={(e) => set('auto_update', e.target.checked)} />
            {t('Aggiornamento automatico')}
          </label>
          <span className="hint">
            {t('Installa da solo le versioni nuove appena le trova, con backup del database prima e ritorno alla versione precedente se qualcosa va storto. Spento: lo script controlla e basta, aggiorni tu con «Aggiorna ora».')}
          </span>
        </div>
        <label className="field">
          <span className="field__label">{t('Controlla GitHub')}</span>
          <select className="input" value={form.check_interval_minutes} disabled={disabled}
            onChange={(e) => set('check_interval_minutes', Number(e.target.value))}>
            {intervals.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
          </select>
        </label>
        <label className="field">
          <span className="field__label">{t('Branch')}</span>
          <input className="input" value={form.branch} disabled={disabled} required maxLength={100}
            onChange={(e) => set('branch', e.target.value.trim())} />
          <span className="hint">{t('Di solito main. Cambiandolo, il prossimo aggiornamento passa a quel branch.')}</span>
        </label>
        <label className="field">
          <span className="field__label">{t('Backup del database da tenere')}</span>
          <input className="input" type="number" min={1} max={100} value={form.keep_backups} disabled={disabled}
            onChange={(e) => set('keep_backups', Number(e.target.value))} />
          <span className="hint">{t('Uno prima di ogni aggiornamento; i più vecchi vengono cancellati.')}</span>
        </label>
      </div>
      <ErrorBox error={error} />
      <div className="update-actions">
        <button type="submit" className="btn btn--primary" disabled={disabled || saving || !changed}>
          {saving ? t('Salvataggio…') : t('Salva impostazioni')}
        </button>
        {saved && <span className="hint">{t('Salvate: valgono dal prossimo giro dello script, entro un minuto.')}</span>}
      </div>
    </form>
  )
}

function History({ items }) {
  if (!items?.length) return <p className="empty">{t('Ancora nessun aggiornamento.')}</p>
  return (
    <div className="table-wrap">
      <table className="table table--dense">
        <thead>
          <tr>
            <th>{t('Quando')}</th>
            <th>{t('Da')}</th>
            <th>{t('A')}</th>
            <th>{t('Avvio')}</th>
            <th>{t('Esito')}</th>
            <th>{t('Dettagli')}</th>
          </tr>
        </thead>
        <tbody>
          {items.map((item) => {
            const outcome = OUTCOMES[item.outcome] || { label: item.outcome, tone: 'muted' }
            return (
              <tr key={item.started_at}>
                <td>{formatDateTime(item.started_at)}</td>
                <td><code title={item.from?.commit}>{item.from?.version || item.from?.short}</code></td>
                <td><code title={item.to?.commit}>{item.to?.version || item.to?.short}</code></td>
                <td>{item.trigger === 'auto' ? t('Automatico') : t('A mano')}{item.requested_by ? ` · ${item.requested_by}` : ''}</td>
                <td><span className={`badge badge--${outcome.tone}`}>{outcome.label}</span></td>
                <td>
                  {tMessage(item.message)}
                  {item.backup && <span className="hint update-history__backup">{t('Backup: {file}', { file: item.backup })}{item.db_restored ? ` · ${t('ripristinato')}` : ''}</span>}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

/** Aggiornamenti (solo admin): lo script sull'host fa il lavoro, qui si vede lo stato e si chiede di agire. */
export default function UpdatesPage() {
  const { data: fresh, error, reload } = useApi('/updates')
  // Durante l'aggiornamento l'API si riavvia: tengo l'ultimo stato ricevuto e continuo a chiedere
  const [lastData, setLastData] = useState(null)
  useEffect(() => { if (fresh) setLastData(fresh) }, [fresh])
  const data = fresh || lastData
  const offline = Boolean(error && lastData)
  const [showLog, setShowLog] = useState(false)
  const log = useApi(showLog ? '/updates/log' : null)
  const [confirm, setConfirm] = useState(false)
  const [sending, setSending] = useState(null)
  const [actionError, setActionError] = useState(null)

  const status = data?.status
  const busy = Boolean(status && status.activity && status.activity !== 'idle')
  const waiting = offline || busy || Boolean(data?.request)

  // Aggiorno spesso mentre lo script lavora o ha una richiesta in sospeso, altrimenti ogni tanto
  useEffect(() => {
    const timer = setInterval(() => {
      reload()
      if (showLog) log.reload()
    }, waiting ? 3000 : 20000)
    return () => clearInterval(timer)
  }, [waiting, showLog, reload, log.reload]) // eslint-disable-line react-hooks/exhaustive-deps

  const send = async (action) => {
    setSending(action)
    setActionError(null)
    try {
      await api.post('/updates/request', { action })
      setConfirm(false)
      reload()
    } catch (err) {
      setActionError(err)
    } finally {
      setSending(null)
    }
  }

  if (error && !lastData) return <div className="page"><ErrorBox error={error} /></div>
  if (!data) return <Loading />

  const usable = data.mounted
  const available = status?.available
  const canUpdate = usable && !waiting && status?.update_available
  return (
    <div className="page">
      <header className="page-head">
        <div>
          <h1>{t('Aggiornamenti')}</h1>
          <p className="page-intro">
            {t("NetMap si aggiorna da GitHub con uno script che gira sul server, fuori dall'app: qui vedi a che punto è, chiedi un controllo o un aggiornamento e scegli se farlo in automatico.")}
          </p>
        </div>
        <div className="page-head__actions">
          <button type="button" className="btn" disabled={!usable || waiting || sending} onClick={() => send('check')}>
            {sending === 'check' ? t('Invio…') : t('Controlla ora')}
          </button>
          <button type="button" className="btn btn--primary" disabled={!canUpdate || sending} onClick={() => setConfirm(true)}
            title={status?.update_available ? '' : t('Nessun aggiornamento disponibile')}>
            {t('Aggiorna ora')}
          </button>
        </div>
      </header>

      {offline && <p className="notice">{t("NetMap non risponde: se è in corso un aggiornamento si sta riavviando, la pagina si aggiorna da sola.")}</p>}
      <ScriptWarning data={data} />
      <ErrorBox error={actionError} />
      {status?.check_error && (
        <div className="notice notice--warn">
          <strong>{t('Ultimo controllo non riuscito')}:</strong> {tMessage(status.check_error)}{' '}
          {t('Di solito è la deploy key: sul server prova git fetch origin nella cartella di NetMap.')}
        </div>
      )}

      <section className="section">
        <LiveState status={status} request={data.request} />
        <dl className="facts update-facts">
          <div><dt>{t('Versione installata')}</dt><dd><Version info={status?.installed || data.running} /></dd></div>
          <div>
            <dt>{t('Versione disponibile')}</dt>
            <dd>
              {status?.update_available
                ? <><span className="badge badge--info">{t('Aggiornamento disponibile')}</span> <Version info={available} /></>
                : status?.last_check ? <span className="badge badge--ok">{t('Sei aggiornato')}</span> : <span className="muted">—</span>}
            </dd>
          </div>
          <div>
            <dt>{t('Ultimo controllo')}</dt>
            <dd>{status?.last_check ? <>{formatDateTime(status.last_check)} <span className="hint">{formatSince(status.last_check)}</span></> : <span className="muted">{t('Mai')}</span>}</dd>
          </div>
          <div>
            <dt>{t('Script sul server')}</dt>
            <dd>
              {status?.last_run
                ? <>{data.script === 'ok' ? t('Attivo') : t('Fermo')} <span className="hint">{t('ultimo giro {when}', { when: formatSince(status.last_run) })}</span></>
                : <span className="muted">{t('Non rilevato')}</span>}
              {status?.updater?.mode && <span className="hint"> · {t('modalità {mode}', { mode: status.updater.mode })}</span>}
            </dd>
          </div>
        </dl>
      </section>

      <section className="section">
        <header className="section__head"><h2>{t('Impostazioni')}</h2></header>
        <SettingsForm settings={data.settings} disabled={!usable} onSaved={reload} />
      </section>

      <section className="section">
        <header className="section__head">
          <h2>{t('Storico')} <span className="section__count">{t('ultimi 20 aggiornamenti')}</span></h2>
        </header>
        <History items={status?.history} />
      </section>

      <section className="section">
        <header className="section__head">
          <h2>{t('Log')}</h2>
          <div className="page-head__actions">
            <button type="button" className="btn btn--ghost" onClick={() => setShowLog((v) => !v)}>
              {showLog ? t('Nascondi log') : t('Mostra log')}
            </button>
          </div>
        </header>
        {showLog && (
          log.error ? <ErrorBox error={log.error} /> : (
            <pre className="log update-log">{log.data ? log.data.text || t('Il log è vuoto.') : t('Caricamento…')}</pre>
          )
        )}
        {!showLog && <p className="hint">{t("Il log dell'ultimo aggiornamento, più le righe dei controlli successivi.")}</p>}
      </section>

      {confirm && (
        <Modal title={t('Aggiornare NetMap adesso?')} onClose={() => setConfirm(false)}>
          <div className="form">
            <p>
              {t('Da {from} a {to}.', {
                from: status?.installed?.version || status?.installed?.short || '?',
                to: available?.version || available?.short || '?',
              })}
            </p>
            <p className="hint">
              {t("Lo script fa il backup del database, scarica il codice e riavvia l'app: per qualche minuto NetMap non risponde. Se la versione nuova non parte, torna da solo a quella di adesso.")}
            </p>
            <ErrorBox error={actionError} />
            <div className="modal__footer">
              <button type="button" className="btn btn--ghost" onClick={() => setConfirm(false)} disabled={Boolean(sending)}>{t('Annulla')}</button>
              <button type="button" className="btn btn--primary" onClick={() => send('update')} disabled={Boolean(sending)}>
                {sending === 'update' ? t('Invio…') : t('Aggiorna ora')}
              </button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  )
}
