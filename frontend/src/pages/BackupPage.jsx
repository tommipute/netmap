import { useEffect, useState } from 'react'
import { api } from '../api'
import { ErrorBox, Loading } from '../components/Bits'
import { BUSY, ScriptWarning, tMessage, useUpdater } from '../components/UpdaterBits'
import { formatDateTime, formatSince } from '../options'
import { t, tn } from '../i18n'

const KINDS = {
  daily: t('Notturno'),
  manual: t('A mano'),
  update: t('Prima di un aggiornamento'),
}

function formatSize(bytes) {
  if (bytes >= 1024 * 1024 * 1024) return `${(bytes / 1024 ** 3).toFixed(1)} GB`
  if (bytes >= 1024 * 1024) return `${(bytes / 1024 ** 2).toFixed(1)} MB`
  return `${Math.max(1, Math.round(bytes / 1024))} KB`
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
          <span className="hint">{t('Vale per i backup notturni e per quelli fatti a mano. Quelli prima degli aggiornamenti si impostano nella pagina Aggiornamenti.')}</span>
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

/** Backup del database (solo admin): li fa lo script sull'host, qui si vedono e si chiede di farne uno subito. */
export default function BackupPage() {
  const { data, error, offline, waiting, reload, send, sending, actionError } = useUpdater()
  if (error) return <div className="page"><ErrorBox error={error} /></div>
  if (!data) return <Loading />

  const status = data.status
  const backup = status?.backup || {}
  const files = backup.files || []
  const last = backup.last
  const running = status?.activity === 'backup'
  const pending = data.request?.action === 'backup'
  const total = files.reduce((sum, f) => sum + f.size, 0)
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
          <button type="button" className="btn btn--primary" disabled={!data.mounted || waiting || Boolean(sending)} onClick={() => send('backup')}>
            {sending === 'backup' ? t('Invio…') : t('Backup ora')}
          </button>
        </div>
      </header>

      {offline && <p className="notice">{t("NetMap non risponde: se è in corso un aggiornamento si sta riavviando, la pagina si aggiorna da sola.")}</p>}
      <ScriptWarning data={data} />
      <ErrorBox error={actionError} />

      <section className="section">
        <div className="update-live">
          {running ? (
            <><span className="badge badge--info"><span className="update-spinner" aria-hidden="true" />{BUSY.backup}</span></>
          ) : pending ? (
            <><span className="badge badge--muted">{t('In attesa')}</span><span>{t('Backup richiesto')}: {t('lo script lo esegue entro un minuto.')}</span></>
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
                </tr>
              </thead>
              <tbody>
                {files.map((f) => (
                  <tr key={f.file}>
                    <td>{formatDateTime(f.date)}</td>
                    <td>{KINDS[f.kind] || f.kind}</td>
                    <td><code>{f.file}</code></td>
                    <td>{formatSize(f.size)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <div className="notice backup-help">
          <p>
            {t('I file stanno sul server in {dir}. Per ripristinarne uno (NetMap resta ferma un minuto e torna ai dati di quel momento):', { dir: backup.dir || 'backups/' })}
          </p>
          <pre className="log">updater/updater.sh restore backups/{files[0]?.file || 'NOME-DEL-FILE.dump'}</pre>
          <p className="hint">
            {t('Questi backup stanno sullo stesso disco di NetMap: per proteggerti anche da un guasto del server, pianifica in Proxmox un backup della VM su un altro disco.')}
          </p>
        </div>
      </section>
    </div>
  )
}
