import { useEffect, useState } from 'react'
import { api } from '../api'
import { ErrorBox, Loading } from '../components/Bits'
import { Icon } from '../components/Icon'
import Modal from '../components/Modal'
import { BUSY, ScriptWarning, tMessage, useUpdater } from '../components/UpdaterBits'
import { useApi } from '../hooks'
import { formatDateTime, formatSince } from '../options'
import { t } from '../i18n'

const INTERVALS = [
  { value: 15, label: t('Ogni 15 minuti') },
  { value: 30, label: t('Ogni 30 minuti') },
  { value: 60, label: t('Ogni ora') },
  { value: 180, label: t('Ogni 3 ore') },
  { value: 360, label: t('Ogni 6 ore') },
  { value: 720, label: t('Ogni 12 ore') },
  { value: 1440, label: t('Una volta al giorno') },
]
const REQUESTED = {
  update: t('Aggiornamento richiesto'),
  check: t('Controllo richiesto'),
  backup: t('Backup richiesto'),
  diagnostics: t('Raccolta dei log richiesta'),
}
const OUTCOMES = {
  success: { label: t('Completato'), tone: 'ok' },
  error: { label: t('Errore'), tone: 'danger' },
  rolled_back: { label: t('Rollback eseguito'), tone: 'warn' },
}

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
        <span>{REQUESTED[request.action] || t('Controllo richiesto')}: {t('lo script lo esegue entro un minuto.')}</span>
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

const CHANNELS = [
  { value: 'stable', label: t('Stabile') },
  { value: 'beta', label: t('Beta (anche le versioni di prova)') },
  // Solo installazioni dal codice: per ogni singola modifica non ci sono immagini pronte
  { value: 'dev', label: t('Sviluppo (ogni modifica, anche non provata)'), source: true },
]

function SettingsForm({ settings, mode, disabled, onSaved }) {
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
          <span className="field__label">{t('Controlla gli aggiornamenti')}</span>
          <select className="input" value={form.check_interval_minutes} disabled={disabled}
            onChange={(e) => set('check_interval_minutes', Number(e.target.value))}>
            {intervals.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
          </select>
        </label>
        <label className="field">
          <span className="field__label">{t('Canale')}</span>
          <select className="input" value={form.channel} disabled={disabled} onChange={(e) => set('channel', e.target.value)}>
            {CHANNELS.filter((o) => mode !== 'image' || !o.source || form.channel === o.value)
              .map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
          </select>
          <span className="hint">
            {form.channel === 'dev'
              ? t('Ogni modifica del branch {branch} appena è su GitHub, prima che diventi una release: solo per un server di prova.', { branch: form.branch || 'main' })
              : t('Si installano solo versioni più nuove di quella attuale: tornando a Stabile resti dove sei finché non esce una stabile più recente.')}
          </span>
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

/**
 * Pacchetto diagnostico: lo zip lo prepara l'API; i log dei container (e lo stato dell'host) li deve raccogliere lo
 * script, perché dall'app Docker non si vede.
 */
function Diagnostics({ status, disabled, sending, onCollect }) {
  const collected = status?.diagnostics
  return (
    <section className="section">
      <header className="section__head"><h2>{t('Diagnostica')}</h2></header>
      <p className="hint">
        {t('Un file zip da allegare a una segnalazione: versione, configurazione (senza password né chiavi), stato del database e log. I log possono contenere indirizzi IP e nomi della tua rete: dagli un\'occhiata prima di mandarlo.')}
      </p>
      <div className="update-actions">
        <button type="button" className="btn" disabled={disabled} onClick={onCollect}>
          {sending ? t('Invio…') : t('Raccogli i log dei container')}
        </button>
        <a className="btn btn--primary" href="/api/diagnostics" download><Icon name="download" /> {t('Scarica il pacchetto diagnostico')}</a>
        <span className="hint">
          {collected?.at
            ? t('Log dei container raccolti il {when}: sono nel pacchetto.', { when: formatDateTime(collected.at) })
            : t("Senza raccoglierli il pacchetto ha solo i log dell'API e dello script.")}
        </span>
      </div>
    </section>
  )
}

/** Aggiornamenti (solo admin): lo script sull'host fa il lavoro, qui si vede lo stato e si chiede di agire. */
export default function UpdatesPage() {
  const { data, error, offline, waiting, reload, send: request, sending, actionError } = useUpdater()
  const [showLog, setShowLog] = useState(false)
  const log = useApi(showLog ? '/updates/log' : null)
  const [confirm, setConfirm] = useState(false)
  const status = data?.status

  // Il log segue lo stesso ritmo della pagina
  useEffect(() => {
    if (!showLog) return undefined
    const timer = setInterval(log.reload, waiting ? 3000 : 20000)
    return () => clearInterval(timer)
  }, [showLog, waiting, log.reload])

  const send = async (action) => {
    if (await request(action)) setConfirm(false)
  }

  if (error && !data) return <div className="page"><ErrorBox error={error} /></div>
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
            {t("NetMap si aggiorna con uno script che gira sul server, fuori dall'app: qui vedi a che punto è, chiedi un controllo o un aggiornamento e scegli se farlo in automatico.")}
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
          {status.updater?.mode === 'image'
            ? t('Di solito è il registro delle immagini: sul server prova docker compose pull nella cartella di NetMap.')
            : t('Di solito è la deploy key: sul server prova git fetch origin nella cartella di NetMap.')}
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
        <SettingsForm settings={data.settings} mode={status?.updater?.mode} disabled={!usable} onSaved={reload} />
      </section>

      <section className="section">
        <header className="section__head">
          <h2>{t('Storico')} <span className="section__count">{t('ultimi 20 aggiornamenti')}</span></h2>
        </header>
        <History items={status?.history} />
      </section>

      <Diagnostics status={status} disabled={!usable || waiting || Boolean(sending)} sending={sending === 'diagnostics'}
        onCollect={() => send('diagnostics')} />

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
              {t("Lo script fa il backup del database, scarica la versione nuova e riavvia l'app: per qualche minuto NetMap non risponde. Se la versione nuova non parte, torna da solo a quella di adesso.")}
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
