import { useEffect, useId, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'
import { useAuth } from '../auth'
import { ErrorBox, Loading } from '../components/Bits'
import { Icon, PageIcon } from '../components/Icon'
import { useApi } from '../hooks'
import { SMTP_SECURITY } from '../resources'
import { t, tServer, tn } from '../i18n'

const DEFAULT_PORT = { starttls: '587', ssl: '465', none: '25' }

const pick = (data) => ({
  host: data.host ?? '', port: data.port ?? '', security: data.security || 'starttls',
  username: data.username ?? '', sender: data.sender ?? '', password: '',
})

/** Il modulo come lo vuole l'API: vuoti = null, porta numerica, password solo se scritta (assente = invariata) */
function payload(form) {
  const out = {
    host: form.host.trim() || null,
    port: form.port === '' ? null : Number(form.port),
    security: form.security,
    username: form.username.trim() || null,
    sender: form.sender.trim() || null,
  }
  if (form.password) out.password = form.password
  return out
}

function TextField({ label, value, onChange, hint, placeholder, type = 'text', required, autoComplete }) {
  const id = useId()
  return (
    <div className="field">
      <label className="field__label" htmlFor={id}>
        {label}
        {required && <span className="field__req" aria-hidden="true"> *</span>}
      </label>
      <input id={id} className="input" type={type} value={value} placeholder={placeholder} autoComplete={autoComplete}
        onChange={(e) => onChange(e.target.value)} />
      {hint && <span className="hint">{hint}</span>}
    </div>
  )
}

/** Email di prova con le impostazioni del modulo, anche non salvate. */
function MailTest({ form }) {
  const { user } = useAuth()
  const [to, setTo] = useState(user?.email || '')
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)

  const submit = async (e) => {
    e.preventDefault()
    setBusy(true)
    setError(null)
    setResult(null)
    try {
      setResult(await api.post('/mail-settings/test', { settings: payload(form), to: to.trim() }))
    } catch (err) {
      setError(err)
    } finally {
      setBusy(false)
    }
  }

  return (
    <form className="form" onSubmit={submit}>
      <p className="hint">{t('Manda un\'email con le impostazioni scritte qui sopra, anche se non le hai ancora salvate. Non salva niente.')}</p>
      <div className="form__grid">
        <TextField label={t('Destinatario')} type="email" value={to} onChange={setTo} placeholder={t('it@azienda.it')} />
      </div>
      <ErrorBox error={error} />
      <div className="update-actions">
        <button type="submit" className="btn" disabled={busy || !to.includes('@') || !form.host.trim()}>
          <Icon name="send" /> {busy ? t('Invio in corso…') : t('Invia email di prova')}
        </button>
        {result?.ok && <span className="badge badge--ok">{t('Inviata: controlla la casella di posta')}</span>}
        {result && !result.ok && (
          <span className="update-live">
            <span className="badge badge--danger">{t('Non riuscito')}</span>
            <span>{tServer(result.message)}</span>
          </span>
        )}
      </div>
    </form>
  )
}

export default function MailPage() {
  const { data, error, reload } = useApi('/mail-settings')
  const [form, setForm] = useState(null)
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState(null)
  const [saved, setSaved] = useState(false)
  useEffect(() => {
    if (data) setForm(pick(data))
  }, [data])

  if (error) return <div className="page"><ErrorBox error={error} /></div>
  if (!data || !form) return <Loading />

  const set = (name, value) => {
    setForm((prev) => ({ ...prev, [name]: value }))
    setSaved(false)
  }
  const changed = JSON.stringify(payload(form)) !== JSON.stringify(payload(pick(data)))

  const submit = async (e) => {
    e.preventDefault()
    setSaving(true)
    setSaveError(null)
    try {
      await api.put('/mail-settings', payload(form))
      setSaved(true)
      reload()
    } catch (err) {
      setSaveError(err)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="page mail-page">
      <header className="page-head">
        <div>
          <h1 className="page-title"><PageIcon name="mail" />{t('Email')}</h1>
          <p className="page-intro">
            {t('Il server di posta con cui NetMap manda le email: lo usano i canali di avviso email, che così hanno bisogno solo dei destinatari. Un canale può comunque usare un server suo.')}
          </p>
        </div>
      </header>

      <p className="notice">
        {data.channels || data.custom_channels ? (
          <>
            {tn(data.channels, '1 canale email usa questo server.', '{n} canali email usano questo server.')}
            {data.custom_channels > 0 && <> {tn(data.custom_channels, '1 canale ha un server suo.', '{n} canali hanno un server loro.')}</>}
          </>
        ) : t('Nessun canale email per ora.')}{' '}
        <Link to="/alert-channels?type=email">{t('Vedi i canali')}</Link>
      </p>

      <form className="form" onSubmit={submit}>
        <section className="section">
          <header className="section__head"><h2>{t('Server di posta')}</h2></header>
          <div className="form__grid">
            <TextField label={t('Server SMTP')} value={form.host} onChange={(v) => set('host', v)} placeholder={t('smtp.azienda.it')}
              required={data.channels > 0} hint={t('Nome o indirizzo del server, per esempio quello di Exchange o di Microsoft 365 (smtp.office365.com).')} />
            <div className="field">
              <label className="field__label" htmlFor="mail-security">{t('Sicurezza')}</label>
              <select id="mail-security" className="input" value={form.security} onChange={(e) => set('security', e.target.value)}>
                {SMTP_SECURITY.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
              </select>
            </div>
            <TextField label={t('Porta')} type="number" value={form.port} onChange={(v) => set('port', v)} placeholder={DEFAULT_PORT[form.security]}
              hint={t('Vuota = {port}.', { port: DEFAULT_PORT[form.security] })} />
            <TextField label={t('Mittente')} value={form.sender} onChange={(v) => set('sender', v)} placeholder={t('netmap@azienda.it')}
              hint={t('Vuoto = l\'utente SMTP.')} />
            <TextField label={t('Utente SMTP')} value={form.username} onChange={(v) => set('username', v)} autoComplete="off"
              hint={t('Vuoto = senza autenticazione (relay interno).')} />
            <TextField label={t('Password SMTP')} type="password" value={form.password} onChange={(v) => set('password', v)} autoComplete="new-password"
              placeholder={data.has_password ? t('Salvata: lascia vuoto per non cambiarla') : undefined} />
          </div>
        </section>

        <ErrorBox error={saveError} />
        <div className="update-actions">
          <button type="submit" className="btn btn--primary" disabled={saving || !changed}>
            {saving ? t('Salvataggio…') : t('Salva impostazioni')}
          </button>
          {saved && <span className="hint">{t('Salvate.')}</span>}
        </div>
      </form>

      <section className="section">
        <header className="section__head"><h2>{t('Prova')}</h2></header>
        <MailTest form={form} />
      </section>
    </div>
  )
}
