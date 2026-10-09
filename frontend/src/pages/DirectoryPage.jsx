import { useEffect, useId, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'
import { ROLES, useAuth } from '../auth'
import { ErrorBox, Loading } from '../components/Bits'
import { Icon } from '../components/Icon'
import { useApi } from '../hooks'
import { labelOf } from '../options'
import { t, tServer, tn } from '../i18n'

const FIELDS = ['enabled', 'servers', 'security', 'port', 'verify_cert', 'ca_cert', 'domain', 'base_dn',
  'admin_group', 'editor_group', 'viewer_group', 'default_role']

const SECURITY = [
  { value: 'ldaps', label: t('LDAPS (porta 636)') },
  { value: 'starttls', label: t('StartTLS (porta 389)') },
  { value: 'none', label: t('In chiaro (porta 389, sconsigliato)') },
]

const GROUP_FIELDS = [
  { name: 'admin_group', role: 'admin', placeholder: 'NetMap-Admin' },
  { name: 'editor_group', role: 'editor', placeholder: 'NetMap-Editor' },
  { name: 'viewer_group', role: 'viewer', placeholder: 'NetMap-Viewer' },
]

const pick = (data) => Object.fromEntries(FIELDS.map((name) => [name, data[name] ?? (name === 'port' ? '' : data[name])]))

/** Il modulo come lo vuole l'API: campi vuoti = null, porta numerica */
function payload(form) {
  const out = { ...form }
  for (const name of ['ca_cert', 'base_dn', 'admin_group', 'editor_group', 'viewer_group', 'default_role']) {
    out[name] = (out[name] || '').trim() || null
  }
  out.port = out.port === '' || out.port == null ? null : Number(out.port)
  out.servers = (out.servers || '').trim()
  out.domain = (out.domain || '').trim()
  return out
}

/** DC=azienda,DC=local dal dominio: è la base di ricerca quando il campo è vuoto */
const domainDn = (domain) => (domain || '').trim().replace(/\.$/, '').split('.').filter(Boolean).map((p) => `DC=${p}`).join(',')

function TextField({ label, value, onChange, hint, placeholder, mono, required, type = 'text' }) {
  const id = useId()
  return (
    <div className="field">
      <label className="field__label" htmlFor={id}>
        {label}
        {required && <span className="field__req" aria-hidden="true"> *</span>}
      </label>
      <input id={id} className={`input${mono ? ' mono' : ''}`} type={type} value={value ?? ''} placeholder={placeholder}
        onChange={(e) => onChange(e.target.value)} />
      {hint && <span className="hint">{hint}</span>}
    </div>
  )
}

/** Prova con un utente vero, con le impostazioni del modulo (anche non salvate). */
function DirectoryTest({ form }) {
  const [login, setLogin] = useState({ username: '', password: '' })
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)

  const submit = async (e) => {
    e.preventDefault()
    setBusy(true)
    setError(null)
    setResult(null)
    try {
      setResult(await api.post('/directory/test', { settings: payload(form), ...login }))
    } catch (err) {
      setError(err)
    } finally {
      setBusy(false)
    }
  }

  return (
    <form className="form" onSubmit={submit}>
      <p className="hint directory-test__intro">{t('Si collega al dominio con le impostazioni scritte qui sopra, anche se non le hai ancora salvate, e dice che ruolo avrebbe questo utente. Non salva niente.')}</p>
      <div className="form__grid">
        <TextField label={t('Utente del dominio')} value={login.username} placeholder="mario.rossi"
          onChange={(v) => setLogin((prev) => ({ ...prev, username: v }))} />
        <TextField label={t('Password')} type="password" value={login.password}
          onChange={(v) => setLogin((prev) => ({ ...prev, password: v }))} />
      </div>
      <ErrorBox error={error} />
      <div className="update-actions">
        <button type="submit" className="btn" disabled={busy || !login.username || !login.password}>
          <Icon name="key" /> {busy ? t('Prova in corso…') : t('Prova con questo utente')}
        </button>
      </div>
      {result && !result.ok && (
        <div className="update-live">
          <span className="badge badge--danger">{t('Non riuscito')}</span>
          <span>{tServer(result.message)}</span>
        </div>
      )}
      {result?.ok && (
        <div className="directory-result">
          <div className="update-live">
            {result.role ? (
              <span className="badge badge--ok">{t('Entra come {role}', { role: labelOf(ROLES, result.role) })}</span>
            ) : (
              <span className="badge badge--warn">{t('Password giusta, ma non entra')}</span>
            )}
            <span>
              <strong>{result.user.full_name || result.user.username}</strong> <span className="muted">{result.user.username}</span>
            </span>
            {result.by_default && <span className="hint">{t('Non è in nessuno dei gruppi: vale il ruolo per tutti gli altri.')}</span>}
            {!result.role && <span className="hint">{t('Non è in nessuno dei gruppi e non hai scelto un ruolo per tutti gli altri.')}</span>}
          </div>
          <p className="hint mono directory-dn">{result.user.dn}</p>
          {result.groups.length > 0 && (
            <div className="table-wrap">
              <table className="table table--dense">
                <thead>
                  <tr><th>{t('Ruolo')}</th><th>{t('Gruppo')}</th><th>{t('Nel dominio')}</th><th>{t("L'utente ne fa parte")}</th></tr>
                </thead>
                <tbody>
                  {result.groups.map((g) => (
                    <tr key={g.role}>
                      <td>{labelOf(ROLES, g.role)}</td>
                      <td className="mono">{g.group}</td>
                      <td>{g.found ? t('trovato') : <span className="backup-msg--error">{t('non trovato')}</span>}</td>
                      <td>{g.member ? <strong>{t('sì')}</strong> : <span className="muted">{t('no')}</span>}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </form>
  )
}

export default function DirectoryPage() {
  const { user } = useAuth()
  const { data, error, reload } = useApi('/directory')
  const [form, setForm] = useState(null)
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState(null)
  const [saved, setSaved] = useState(false)
  const fileInput = useRef(null)
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
      await api.put('/directory', payload(form))
      setSaved(true)
      reload()
    } catch (err) {
      setSaveError(err)
    } finally {
      setSaving(false)
    }
  }

  const readCert = async (file) => {
    const text = await file.text()
    if (!text.includes('-----BEGIN CERTIFICATE-----')) {
      setSaveError(new Error(t('Il file non è un certificato in formato Base64 (PEM): in Windows esportalo come "X.509 codificato Base-64 (.CER)".')))
      return
    }
    setSaveError(null)
    set('ca_cert', text.trim())
  }

  const securityOff = form.security === 'none'
  const defaultPort = form.security === 'ldaps' ? '636' : '389'

  return (
    <div className="page directory-page">
      <header className="page-head">
        <div>
          <h1>{t('Active Directory')}</h1>
          <p className="page-intro">
            {t('Accesso a NetMap con gli utenti di Windows del dominio: la password la controlla il domain controller e il ruolo viene dai gruppi, a ogni accesso. Gli utenti locali, come l\'amministratore creato all\'installazione, entrano sempre con la loro password, anche se il dominio non risponde.')}
          </p>
        </div>
      </header>

      {data.enabled && data.local_admins === 0 && (
        <p className="notice notice--warn">
          {t('Nessun amministratore locale attivo: se il dominio non risponde nessuno può gestire NetMap. Creane uno in Utenti, con una password solo sua.')}
        </p>
      )}
      {data.domain_users > 0 && (
        <p className="notice">
          {tn(data.domain_users, '1 utente di dominio ha già fatto accesso.', '{n} utenti di dominio hanno già fatto accesso.')}{' '}
          <Link to="/users?source=ad">{t('Vedi gli utenti')}</Link>
        </p>
      )}

      <form className="form" onSubmit={submit}>
        <section className="section">
          <header className="section__head"><h2>{t('Dominio')}</h2></header>
          <div className="form__grid">
            <div className="field field--wide">
              <label className="check">
                <input type="checkbox" checked={form.enabled} onChange={(e) => set('enabled', e.target.checked)} />
                {t('Accesso con Active Directory attivo')}
              </label>
              <span className="hint">{t('Spento, gli utenti di dominio non entrano più; i loro utenti in NetMap restano (e lo storico con loro).')}</span>
            </div>
            <TextField label={t('Dominio')} value={form.domain} onChange={(v) => set('domain', v)} placeholder="azienda.local" required={form.enabled}
              hint={t('Nome DNS del dominio. Si entra con mario.rossi, AZIENDA\\mario.rossi o mario.rossi@azienda.local.')} />
            <TextField label={t('Domain controller')} value={form.servers} onChange={(v) => set('servers', v)} required={form.enabled}
              placeholder="dc1.azienda.local, dc2.azienda.local"
              hint={t('Nome completo, quello scritto nel certificato. Più server separati da virgola: vale il primo che risponde.')} />
            <div className="field">
              <label className="field__label" htmlFor="directory-security">{t('Connessione')}</label>
              <select id="directory-security" className="input" value={form.security} onChange={(e) => set('security', e.target.value)}>
                {SECURITY.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
              </select>
              {securityOff
                ? <span className="hint backup-msg--error">{t('Le password passano in chiaro sulla rete, e i domain controller recenti rifiutano questo accesso. Solo per prova.')}</span>
                : <span className="hint">{t('LDAPS e StartTLS cifrano la password. Serve che il domain controller abbia un certificato (Servizi certificati di Active Directory).')}</span>}
            </div>
            <TextField label={t('Porta')} type="number" value={form.port} onChange={(v) => set('port', v)} placeholder={defaultPort}
              hint={t('Vuota = {port}.', { port: defaultPort })} />
            {!securityOff && (
              <div className="field field--wide">
                <label className="check">
                  <input type="checkbox" checked={form.verify_cert} onChange={(e) => set('verify_cert', e.target.checked)} />
                  {t('Verifica il certificato del domain controller')}
                </label>
                <span className={`hint${form.verify_cert ? '' : ' backup-msg--error'}`}>
                  {form.verify_cert
                    ? t('Così nessuno può fingersi il domain controller e leggere le password.')
                    : t('Senza verifica chi si mette in mezzo sulla rete può leggere le password: spegnila solo per prova.')}
                </span>
              </div>
            )}
            {!securityOff && form.verify_cert && (
              <div className="field field--wide">
                <span className="field__label">
                  {t('Certificato della CA del dominio')}
                  <button type="button" className="link-button directory-file" onClick={() => fileInput.current?.click()}>
                    {t('Carica da file')}
                  </button>
                </span>
                <input ref={fileInput} type="file" accept=".pem,.crt,.cer" hidden
                  onChange={(e) => { const f = e.target.files[0]; e.target.value = ''; if (f) readCert(f) }} />
                <textarea className="input mono" rows={form.ca_cert ? 6 : 3} value={form.ca_cert ?? ''} spellCheck={false}
                  aria-label={t('Certificato della CA del dominio')} placeholder="-----BEGIN CERTIFICATE-----"
                  onChange={(e) => set('ca_cert', e.target.value)} />
                <span className="hint">{t('Il certificato della CA che firma quelli dei domain controller, in Base64 (PEM). Vuoto = solo le CA pubbliche conosciute dal sistema.')}</span>
              </div>
            )}
            <TextField label={t('Base di ricerca')} value={form.base_dn} onChange={(v) => set('base_dn', v)} mono
              placeholder={domainDn(form.domain) || 'OU=Utenti,DC=azienda,DC=local'}
              hint={t('Facoltativa: entra solo chi sta sotto questa unità organizzativa. Vuota = tutto il dominio.')} />
          </div>
        </section>

        <section className="section">
          <header className="section__head"><h2>{t('Ruoli dai gruppi')}</h2></header>
          <p className="hint">{t('Nome del gruppo di Active Directory (o il suo DN completo). Valgono anche i gruppi dentro il gruppo. Chi è in più gruppi prende il ruolo più alto.')}</p>
          <div className="form__grid">
            {GROUP_FIELDS.map((g) => (
              <TextField key={g.name} label={t('Gruppo: {role}', { role: labelOf(ROLES, g.role) })} value={form[g.name]}
                onChange={(v) => set(g.name, v)} placeholder={g.placeholder} />
            ))}
            <div className="field">
              <label className="field__label" htmlFor="directory-default-role">{t('Chi non è in nessuno di questi gruppi')}</label>
              <select id="directory-default-role" className="input" value={form.default_role ?? ''} onChange={(e) => set('default_role', e.target.value || null)}>
                <option value="">{t('Non entra')}</option>
                {ROLES.map((o) => <option key={o.value} value={o.value}>{t('Entra come {role}', { role: o.label })}</option>)}
              </select>
            </div>
          </div>
        </section>

        <ErrorBox error={saveError} />
        <div className="update-actions">
          <button type="submit" className="btn btn--primary" disabled={saving || !changed}>
            {saving ? t('Salvataggio…') : t('Salva impostazioni')}
          </button>
          {saved && <span className="hint">{form.enabled ? t('Salvate: valgono dal prossimo accesso.') : t('Salvate.')}</span>}
          {user?.source === 'ad' && <span className="hint">{t('Sei entrato con Active Directory: se lo spegni, la sessione resta aperta fino a quando esci.')}</span>}
        </div>
      </form>

      <section className="section directory-test">
        <header className="section__head"><h2>{t('Prova')}</h2></header>
        <DirectoryTest form={form} />
      </section>
    </div>
  )
}
