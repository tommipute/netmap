import { useEffect, useRef, useState } from 'react'
import { api } from '../api'
import { ErrorBox, Loading } from '../components/Bits'
import DeleteDialog from '../components/DeleteDialog'
import { Icon, IconButton } from '../components/Icon'
import Modal from '../components/Modal'
import ResourceForm from '../components/ResourceForm'
import { BUSY, ScriptWarning, tMessage, useUpdater } from '../components/UpdaterBits'
import { useApi } from '../hooks'
import { formatDateTime, formatSince, labelOf } from '../options'
import { BACKUP_TARGET_TYPES } from '../resources'
import { t, tServer, tn } from '../i18n'

const KINDS = {
  daily: t('Notturno'),
  manual: t('A mano'),
  update: t('Prima di un aggiornamento'),
  restore: t('Prima di un ripristino'),
  imported: t('Caricato o riportato'),
}

const RESTORE_OUTCOME = {
  success: { tone: 'ok', label: t('Ripristinato') },
  rolled_back: { tone: 'warn', label: t('Annullato') },
  error: { tone: 'danger', label: t('Errore') },
}

const TASK_LABEL = { sync: t('Copia'), fetch: t('Riporta sul server') }
const TASK_STATUS = {
  queued: { tone: 'muted', label: t('In attesa') },
  running: { tone: 'info', label: t('In corso') },
  done: { tone: 'ok', label: t('Fatto') },
  error: { tone: 'danger', label: t('Errore') },
}

function formatSize(bytes) {
  if (bytes >= 1024 * 1024 * 1024) return `${(bytes / 1024 ** 3).toFixed(1)} GB`
  if (bytes >= 1024 * 1024) return `${(bytes / 1024 ** 2).toFixed(1)} MB`
  return `${Math.max(1, Math.round(bytes / 1024))} KB`
}

/** \\nas\backup\netmap oppure sftp://utente@server:porta/cartella */
function destination(target) {
  const folder = (target.folder || '').replace(/^[\\/]+|[\\/]+$/g, '')
  if (target.type === 'smb') {
    const port = target.port && target.port !== 445 ? `:${target.port}` : ''
    return `\\\\${target.host}${port}\\${target.share}${folder ? `\\${folder.replace(/\//g, '\\')}` : ''}`
  }
  const port = target.port && target.port !== 22 ? `:${target.port}` : ''
  return `sftp://${target.username}@${target.host}${port}/${folder}`
}

function BackupSettings({ settings, disabled, onSaved }) {
  const pick = (s) => ({ backup_daily: s.backup_daily, backup_time: s.backup_time, backup_keep_days: s.backup_keep_days })
  const [form, setForm] = useState(() => pick(settings))
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)
  const [saved, setSaved] = useState(false)
  useEffect(() => setForm(pick(settings)), [settings])
  const set = (name, value) => { setForm((prev) => ({ ...prev, [name]: value })); setSaved(false) }
  const changed = JSON.stringify(form) !== JSON.stringify(pick(settings))

  const submit = async (e) => {
    e.preventDefault()
    setSaving(true)
    setError(null)
    try {
      // Le impostazioni sono un file solo: mando anche quelle degli aggiornamenti, invariate
      await api.put('/updates/settings', { ...settings, ...form })
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
            <input type="checkbox" checked={form.backup_daily} disabled={disabled} onChange={(e) => set('backup_daily', e.target.checked)} />
            {t('Backup ogni notte')}
          </label>
          <span className="hint">{t("Se a quell'ora il server è spento, il backup parte appena si riaccende.")}</span>
        </div>
        <label className="field">
          <span className="field__label">{t('Ora del backup')}</span>
          <input className="input" type="time" value={form.backup_time} disabled={disabled || !form.backup_daily} required
            onChange={(e) => set('backup_time', e.target.value)} />
        </label>
        <label className="field">
          <span className="field__label">{t('Giorni da tenere')}</span>
          <input className="input" type="number" min={1} max={365} value={form.backup_keep_days} disabled={disabled} required
            onChange={(e) => set('backup_keep_days', Number(e.target.value))} />
          <span className="hint">{t('Vale per i backup notturni, quelli fatti a mano, quelli caricati e quelli di sicurezza prima di un ripristino. Quelli prima degli aggiornamenti si impostano nella pagina Aggiornamenti.')}</span>
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

/** Conferma del ripristino: NetMap si ferma e torna ai dati del backup (prima lo script ne fa uno di sicurezza). */
function RestoreDialog({ file, onClose, onDone }) {
  const [sending, setSending] = useState(false)
  const [error, setError] = useState(null)
  const submit = async () => {
    setSending(true)
    setError(null)
    try {
      await api.post('/backups/restore', { file: file.file })
      onDone()
    } catch (err) {
      setError(err)
      setSending(false)
    }
  }
  return (
    <Modal title={t('Ripristinare questo backup?')} onClose={onClose}>
      <div className="form">
        <p><code>{file.file}</code> · {formatDateTime(file.date)}</p>
        <p>{t("NetMap si ferma per circa un minuto e torna ai dati di quel momento: le modifiche fatte dopo si perdono. Prima del ripristino lo script fa un backup di sicurezza dello stato attuale (Prima di un ripristino), da cui puoi tornare indietro.")}</p>
        <p className="hint">{t("Se il backup viene da una versione più nuova di NetMap il ripristino non parte; se NetMap non riparte, lo script rimette da solo lo stato di prima.")}</p>
        <ErrorBox error={error} />
        <div className="modal__footer">
          <button type="button" className="btn btn--ghost" onClick={onClose}>{t('Annulla')}</button>
          <button type="button" className="btn btn--danger" disabled={sending} onClick={submit}>
            {sending ? t('Invio…') : t('Ripristina')}
          </button>
        </div>
      </div>
    </Modal>
  )
}

/** File sulla destinazione: si riportano sul server (poi si ripristinano dalla tabella) o se ne usa la chiave. */
function RemoteFilesDialog({ target, onClose, onChanged }) {
  const { data, error, reload } = useApi(`/backup-targets/${target.id}/files`)
  const [busy, setBusy] = useState(null)
  const [message, setMessage] = useState(null)
  const [actionError, setActionError] = useState(null)
  const run = async (file, action) => {
    setBusy(file.file)
    setMessage(null)
    setActionError(null)
    try {
      if (action === 'fetch') {
        await api.post(`/backup-targets/${target.id}/fetch`, { file: file.file })
        setMessage(t('Richiesta mandata: il file compare tra i backup sul server tra pochi secondi.'))
      } else {
        const result = await api.post(`/backup-targets/${target.id}/use-key`, { file: file.file })
        setMessage(t('Ricifrati con la chiave del vecchio server: {fixed}. Ancora illeggibili: {left}.', { fixed: result.fixed, left: result.unreadable }))
      }
      onChanged()
    } catch (err) {
      setActionError(err)
    } finally {
      setBusy(null)
    }
  }
  return (
    <Modal title={t('Backup su {name}', { name: target.name })} onClose={onClose} wide>
      <div className="form">
        <p className="hint mono">{destination(target)}</p>
        {error && <ErrorBox error={error} />}
        {!data && !error && <Loading />}
        {data && data.length === 0 && <p className="empty">{t('Nessun backup di NetMap in questa cartella.')}</p>}
        {data && data.length > 0 && (
          <div className="table-wrap">
            <table className="table table--dense">
              <thead>
                <tr><th>{t('Quando')}</th><th>{t('File')}</th><th>{t('Dimensione')}</th><th className="table__actions" /></tr>
              </thead>
              <tbody>
                {data.map((f) => (
                  <tr key={f.file}>
                    <td>{f.date ? formatDateTime(f.date) : '—'}</td>
                    <td><code>{f.file}</code>{f.kind === 'key' && <span className="hint"> · {t('chiave dei segreti')}</span>}</td>
                    <td>{formatSize(f.size)}</td>
                    <td className="table__actions">
                      {f.kind === 'key' ? (
                        <button type="button" className="btn btn--sm" disabled={Boolean(busy)} onClick={() => run(f, 'key')}>
                          <Icon name="key" /> {t('Usa questa chiave')}
                        </button>
                      ) : (
                        <button type="button" className="btn btn--sm" disabled={Boolean(busy)} onClick={() => run(f, 'fetch')}>
                          <Icon name="download" /> {t('Riporta sul server')}
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {message && <p className="notice">{message}</p>}
        <ErrorBox error={actionError} />
        <div className="modal__footer">
          <button type="button" className="btn btn--ghost" onClick={reload}>{t('Aggiorna')}</button>
          <button type="button" className="btn btn--primary" onClick={onClose}>{t('Chiudi')}</button>
        </div>
      </div>
    </Modal>
  )
}

function TargetsSection({ targets, overview, reload }) {
  const [dialog, setDialog] = useState(null)
  const [tests, setTests] = useState({}) // id -> 'sending' | {ok, ...} | messaggio d'errore
  const [actionError, setActionError] = useState(null)
  const tasks = overview?.tasks || []
  const names = Object.fromEntries(targets.map((x) => [x.id, x.name]))

  const test = async (target) => {
    setTests((prev) => ({ ...prev, [target.id]: 'sending' }))
    try {
      const result = await api.post(`/backup-targets/${target.id}/test`)
      setTests((prev) => ({ ...prev, [target.id]: result }))
    } catch (err) {
      setTests((prev) => ({ ...prev, [target.id]: err.message }))
    }
    reload()
  }
  const sync = async (target) => {
    setActionError(null)
    try {
      await api.post(`/backup-targets/${target.id}/sync`)
    } catch (err) {
      setActionError(err)
    }
    reload()
  }
  const close = () => setDialog(null)
  const saved = () => { setDialog(null); reload() }

  return (
    <section className="section">
      <header className="section__head">
        <h2>{t('Copie fuori dal server')}</h2>
        <button type="button" className="btn" onClick={() => setDialog({ type: 'new' })}>
          <Icon name="plus" /> {t('Aggiungi destinazione')}
        </button>
      </header>
      <p className="hint">
        {t("NetMap copia da sola ogni backup nuovo su una cartella di rete (NAS, server Windows) o su un server SFTP, entro un minuto da quando è pronto. Così i dati si salvano anche se si guasta il server.")}
      </p>
      {!overview?.mounted && overview && (
        <p className="notice notice--warn">{t('La cartella dei backup non è montata nei container api e worker: aggiorna docker-compose.yml (vedi README, Backup).')}</p>
      )}
      <ErrorBox error={actionError} />
      {targets.length === 0 ? (
        <p className="empty">{t('Nessuna destinazione: i backup restano solo su questo server.')}</p>
      ) : (
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>{t('Nome')}</th>
                <th>{t('Destinazione')}</th>
                <th>{t('Ultima copia')}</th>
                <th className="table__actions" />
              </tr>
            </thead>
            <tbody>
              {targets.map((target) => {
                const result = tests[target.id]
                return (
                  <tr key={target.id}>
                    <td className="backup-target__name">
                      <strong>{target.name}</strong>
                      <div className="hint">
                        {labelOf(BACKUP_TARGET_TYPES, target.type)}
                        {!target.enabled && <> · <span className="badge badge--muted">{t('Disattivata')}</span></>}
                        {target.include_key && <> · {t('con la chiave')}</>}
                      </div>
                    </td>
                    <td className="backup-target__dest"><span className="mono">{destination(target)}</span></td>
                    <td className="backup-target__status">
                      {target.last_error ? (
                        <span className="backup-msg--error">
                          {t('Errore: {error}', { error: tServer(target.last_error) })}
                          <span className="hint"> · {formatSince(target.last_error_at)}</span>
                        </span>
                      ) : target.last_copy_at ? (
                        <span title={formatDateTime(target.last_copy_at)}>{formatSince(target.last_copy_at)}</span>
                      ) : (
                        <span className="muted">{t('Mai')}</span>
                      )}
                      {result === 'sending' && <div className="hint">{t('Prova in corso…')}</div>}
                      {result && typeof result === 'object' && (
                        <div>
                          {t('Connessione riuscita: {n} backup nella cartella.', { n: result.backups })}
                          {result.host_key && (
                            <span className="hint"> {result.host_key_new ? t('Chiave del server registrata: {key}', { key: result.host_key }) : t('Chiave del server: {key}', { key: result.host_key })}</span>
                          )}
                        </div>
                      )}
                      {typeof result === 'string' && result !== 'sending' && <div className="backup-msg--error">{result}</div>}
                    </td>
                    <td className="table__actions">
                      <IconButton icon="play" label={t('Prova la connessione')} small disabled={result === 'sending'} onClick={() => test(target)} />
                      <IconButton icon="upload" label={t('Copia ora i backup che mancano')} small disabled={!target.enabled} onClick={() => sync(target)} />
                      <IconButton icon="search" label={t('Backup sulla destinazione')} small onClick={() => setDialog({ type: 'files', target })} />
                      <IconButton icon="edit" label={t('Modifica')} small onClick={() => setDialog({ type: 'edit', target })} />
                      <IconButton icon="trash" label={t('Elimina')} small danger onClick={() => setDialog({ type: 'delete', target })} />
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
      {tasks.length > 0 && (
        <div className="backup-tasks">
          <h3>{t('Richieste recenti')}</h3>
          <ul>
            {tasks.slice(0, 5).map((task) => (
              <li key={task.id}>
                <span className={`badge badge--${TASK_STATUS[task.status]?.tone || 'muted'}`}>{TASK_STATUS[task.status]?.label || task.status}</span>
                <span>{TASK_LABEL[task.action] || task.action} · {names[task.target_id] || '?'}{task.file ? ` · ${task.file}` : ''}</span>
                {task.message && <span className={task.status === 'error' ? 'backup-msg--error' : 'hint'}>{tServer(task.message)}</span>}
                <span className="hint">{formatSince(task.created_at)}{task.requested_by ? ` · ${task.requested_by}` : ''}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
      {dialog?.type === 'new' && <ResourceForm resourceKey="backup-targets" onClose={close} onSaved={saved} />}
      {dialog?.type === 'edit' && <ResourceForm resourceKey="backup-targets" item={dialog.target} onClose={close} onSaved={saved} />}
      {dialog?.type === 'delete' && (
        <DeleteDialog resourceKey="backup-targets" items={[dialog.target]} onClose={close} onDone={saved}
          note={t('I file già copiati restano sulla destinazione.')} />
      )}
      {dialog?.type === 'files' && <RemoteFilesDialog target={dialog.target} onClose={close} onChanged={reload} />}
    </section>
  )
}

function SecretsSection({ secrets, reload }) {
  const [key, setKey] = useState('')
  const [sending, setSending] = useState(false)
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)
  const submit = async (e) => {
    e.preventDefault()
    setSending(true)
    setError(null)
    setResult(null)
    try {
      setResult(await api.post('/backups/secrets-key/rekey', { key: key.trim() }))
      setKey('')
      reload()
    } catch (err) {
      setError(err)
    } finally {
      setSending(false)
    }
  }
  return (
    <section className="section" id="chiave">
      <header className="section__head"><h2>{t('Chiave dei segreti')}</h2></header>
      <p className="hint">
        {t("Password e community SNMP salvate in NetMap sono cifrate con una chiave che sta sul server, non nel database. Per ripristinare un backup su un altro server serve anche questa chiave: scaricala e tienila in un posto sicuro, oppure attiva «Copia anche la chiave dei segreti» in una destinazione.")}
      </p>
      <div className="update-actions">
        <a className="btn" href="/api/backups/secrets-key" download><Icon name="key" /> {t('Scarica la chiave')}</a>
        {secrets && <span className="hint">{t('Impronta: {fp}', { fp: secrets.fingerprint })}</span>}
      </div>
      {secrets?.unreadable > 0 && (
        <form className="form backup-rekey" onSubmit={submit}>
          <p className="notice notice--warn">
            <strong>{tn(secrets.unreadable, '1 password o community salvata non si legge.', '{n} password o community salvate non si leggono.')}</strong>{' '}
            {t("Il database viene da un altro server (o la chiave è cambiata). Incolla qui la chiave del vecchio server, oppure usa quella copiata su una destinazione (pulsante Backup sulla destinazione): i valori vengono ricifrati con la chiave di adesso.")}
          </p>
          <label className="field">
            <span className="field__label">{t('Chiave del vecchio server')}</span>
            <input className="input mono" value={key} onChange={(e) => setKey(e.target.value)} autoComplete="off" spellCheck={false}
              placeholder={t('Il contenuto del file netmap-secrets-….key (44 caratteri)')} />
          </label>
          <div className="update-actions">
            <button type="submit" className="btn btn--primary" disabled={sending || !key.trim()}>{sending ? t('Invio…') : t('Ricifra')}</button>
          </div>
        </form>
      )}
      {result && (
        <p className="notice">{t('Ricifrati con la chiave del vecchio server: {fixed}. Ancora illeggibili: {left}.', { fixed: result.fixed, left: result.unreadable })}</p>
      )}
      <ErrorBox error={error} />
    </section>
  )
}

/** Caricamento di un backup da questo computer: XMLHttpRequest per vedere l'avanzamento dei file grandi. */
function useUpload(onDone) {
  const [progress, setProgress] = useState(null)
  const [error, setError] = useState(null)
  const upload = (file) => {
    setError(null)
    setProgress(0)
    const xhr = new XMLHttpRequest()
    xhr.open('PUT', `/api/backups/upload?name=${encodeURIComponent(file.name)}`)
    xhr.setRequestHeader('Content-Type', 'application/octet-stream')
    xhr.upload.onprogress = (e) => e.lengthComputable && setProgress(Math.round((e.loaded / e.total) * 100))
    xhr.onload = () => {
      setProgress(null)
      if (xhr.status >= 200 && xhr.status < 300) {
        onDone(JSON.parse(xhr.responseText).file)
        return
      }
      let detail = null
      try { detail = JSON.parse(xhr.responseText).detail } catch { /* risposta non JSON (es. proxy) */ }
      setError(new Error(typeof detail === 'string' ? tServer(detail) : t('Errore {status}', { status: xhr.status })))
    }
    xhr.onerror = () => {
      setProgress(null)
      setError(new Error(t("Impossibile raggiungere l'API: controlla che il backend sia avviato.")))
    }
    xhr.send(file)
  }
  return { upload, progress, error }
}

/** Backup del database (solo admin): li fa lo script sull'host; qui si vedono, si copiano altrove e si ripristinano. */
// Backup fatti prima di un aggiornamento: da quale versione a quale (le note le scrive l'updater; per i backup più
// vecchi c'è solo il commit di partenza, nel nome del file)
function updateText(f) {
  const u = f.update
  const label = (version, commit) => (version && commit ? `${version} (${commit})` : version || commit)
  if (u && (u.from || u.from_commit) && (u.to || u.to_commit)) {
    return t('da {from} a {to}', { from: label(u.from, u.from_commit), to: label(u.to, u.to_commit) })
  }
  const commit = /^netmap-\d{8}-\d{6}-([0-9a-f]{7})\.dump$/.exec(f.file)?.[1]
  return commit ? t('da {from}', { from: commit }) : null
}

export default function BackupPage() {
  const { data, error, offline, waiting, reload, send, sending, actionError } = useUpdater()
  const backups = useApi('/backups')
  const targets = useApi('/backup-targets?limit=100')
  const [restoring, setRestoring] = useState(null)
  const [uploaded, setUploaded] = useState(null)
  const fileInput = useRef(null)
  const reloadAll = () => { reload(); backups.reload(); targets.reload() }
  const { upload, progress, error: uploadError } = useUpload((name) => { setUploaded(name); reloadAll() })

  // Richieste al worker in corso: si aggiorna spesso finché non finiscono
  const busyTasks = (backups.data?.tasks || []).some((task) => task.status === 'queued' || task.status === 'running')
  useEffect(() => {
    const timer = setInterval(() => { backups.reload(); targets.reload() }, busyTasks ? 3000 : 30000)
    return () => clearInterval(timer)
  }, [busyTasks]) // eslint-disable-line react-hooks/exhaustive-deps

  if (error) return <div className="page"><ErrorBox error={error} /></div>
  if (!data) return <Loading />

  const status = data.status
  const backup = status?.backup || {}
  const files = backup.files || []
  const last = backup.last
  const restore = backup.restore
  const activity = status?.activity
  const pending = data.request?.action
  const total = files.reduce((sum, f) => sum + f.size, 0)
  const copies = backups.data?.copies || {}
  const targetList = targets.data?.items || []
  const targetNames = Object.fromEntries(targetList.map((x) => [x.id, x.name]))
  const secrets = backups.data?.secrets
  const restoreOutcome = restore && RESTORE_OUTCOME[restore.outcome]

  return (
    <div className="page">
      <header className="page-head">
        <div>
          <h1>{t('Backup')}</h1>
          <p className="page-intro">
            {t("Copie del database fatte dallo script sul server: ogni notte, prima di ogni aggiornamento e quando lo chiedi tu. Contengono tutti i dati di NetMap, compresi utenti e profili SNMP.")}
          </p>
        </div>
        <div className="page-head__actions">
          <input ref={fileInput} type="file" accept=".dump" hidden onChange={(e) => { const f = e.target.files[0]; e.target.value = ''; if (f) upload(f) }} />
          <button type="button" className="btn" disabled={progress !== null || !backups.data?.mounted} onClick={() => fileInput.current?.click()}>
            <Icon name="upload" /> {progress !== null ? t('Caricamento… {n}%', { n: progress }) : t('Carica un backup')}
          </button>
          <button type="button" className="btn btn--primary" disabled={!data.mounted || waiting || Boolean(sending)} onClick={() => send('backup')}>
            {sending === 'backup' ? t('Invio…') : t('Backup ora')}
          </button>
        </div>
      </header>

      {offline && <p className="notice">{t("NetMap non risponde: se è in corso un aggiornamento o un ripristino si sta riavviando, la pagina si aggiorna da sola.")}</p>}
      <ScriptWarning data={data} />
      <ErrorBox error={actionError} />
      <ErrorBox error={uploadError} />
      {uploaded && <p className="notice">{t('Caricato come {file}: lo trovi nella tabella qui sotto entro un minuto, da lì puoi ripristinarlo.', { file: uploaded })}</p>}
      {secrets?.unreadable > 0 && (
        <p className="notice notice--warn">
          {tn(secrets.unreadable, '1 password o community salvata non si legge: il database viene da un altro server.', '{n} password o community salvate non si leggono: il database viene da un altro server.')}{' '}
          <a href="#chiave">{t('Usa la chiave del vecchio server')}</a>
        </p>
      )}

      <section className="section">
        <div className="update-live">
          {activity && activity !== 'idle' && BUSY[activity] ? (
            <>
              <span className="badge badge--info"><span className="update-spinner" aria-hidden="true" />{BUSY[activity]}</span>
              {status.activity_message && <span>{tMessage(status.activity_message)}</span>}
            </>
          ) : pending === 'backup' || pending === 'restore' ? (
            <>
              <span className="badge badge--muted">{t('In attesa')}</span>
              <span>{pending === 'backup' ? t('Backup richiesto') : t('Ripristino richiesto: {file}', { file: data.request.file })}: {t('lo script lo esegue entro un minuto.')}</span>
            </>
          ) : last ? (
            <>
              <span className={`badge badge--${last.ok ? 'ok' : 'danger'}`}>{last.ok ? t('Riuscito') : t('Errore')}</span>
              <span>{last.ok ? t('Ultimo backup: {file}', { file: last.file }) : tMessage(last.message)}</span>
              <span className="hint">{KINDS[last.kind]} · {formatDateTime(last.at)} · {formatSince(last.at)}</span>
            </>
          ) : (
            <><span className="badge badge--muted">{t('In attesa')}</span><span className="muted">{t('Nessun backup fatto finora.')}</span></>
          )}
        </div>
        {restoreOutcome && activity !== 'restoring' && (
          <div className="update-live">
            <span className={`badge badge--${restoreOutcome.tone}`}>{restoreOutcome.label}</span>
            <span>{tMessage(restore.message)}</span>
            <span className="hint">{t('Ultimo ripristino')} · {formatDateTime(restore.at)}{restore.requested_by ? ` · ${restore.requested_by}` : ''}</span>
          </div>
        )}
      </section>

      <section className="section">
        <header className="section__head"><h2>{t('Impostazioni')}</h2></header>
        <BackupSettings settings={data.settings} disabled={!data.mounted} onSaved={reload} />
      </section>

      <section className="section">
        <header className="section__head">
          <h2>
            {t('Backup sul server')}
            {files.length > 0 && <span className="section__count">{tn(files.length, '1 file', '{n} file')} · {formatSize(total)}</span>}
          </h2>
        </header>
        {files.length === 0 ? (
          <p className="empty">{t('Ancora nessun backup.')}</p>
        ) : (
          <div className="table-wrap">
            <table className="table table--dense">
              <thead>
                <tr>
                  <th>{t('Quando')}</th>
                  <th>{t('Tipo')}</th>
                  <th>{t('File')}</th>
                  <th>{t('Dimensione')}</th>
                  {targetList.length > 0 && <th>{t('Copiato su')}</th>}
                  <th className="table__actions" />
                </tr>
              </thead>
              <tbody>
                {files.map((f) => (
                  <tr key={f.file}>
                    <td>{formatDateTime(f.date)}</td>
                    <td>
                      {KINDS[f.kind] || f.kind}
                      {f.kind === 'update' && updateText(f) && <div className="hint">{updateText(f)}</div>}
                    </td>
                    <td><code>{f.file}</code></td>
                    <td>{formatSize(f.size)}</td>
                    {targetList.length > 0 && (
                      <td>{(copies[f.file] || []).map((id) => targetNames[id]).filter(Boolean).join(', ') || <span className="muted">—</span>}</td>
                    )}
                    <td className="table__actions">
                      <a className="btn btn--icon btn--sm" href={`/api/backups/files/${encodeURIComponent(f.file)}`} download
                        title={t('Scarica')} aria-label={t('Scarica')}><Icon name="download" /></a>
                      <IconButton icon="refresh" label={t('Ripristina questo backup')} small danger
                        disabled={!data.mounted || waiting || !backups.data?.mounted} onClick={() => setRestoring(f)} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <div className="notice backup-help">
          <p>{t('I file stanno sul server in {dir}. Se NetMap non parte e non puoi usare questa pagina, dalla cartella di NetMap sul server:', { dir: backup.dir || 'backups/' })}</p>
          <pre className="log">updater/updater.sh restore backups/{files[0]?.file || 'NOME-DEL-FILE.dump'}</pre>
        </div>
      </section>

      <TargetsSection targets={targetList} overview={backups.data} reload={() => { backups.reload(); targets.reload() }} />
      <SecretsSection secrets={secrets} reload={backups.reload} />

      {restoring && (
        <RestoreDialog file={restoring} onClose={() => setRestoring(null)} onDone={() => { setRestoring(null); reload() }} />
      )}
    </div>
  )
}
