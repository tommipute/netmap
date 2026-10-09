import { useState } from 'react'
import { api } from '../api'
import { useAuth } from '../auth'
import { LANG, LANGUAGES, setLang, t } from '../i18n'
import VersionLabel from '../components/VersionLabel'

/** Accesso; al primo avvio (nessun utente) crea l'amministratore. */
export default function LoginPage() {
  const { setupRequired, directory, signedIn } = useAuth()
  const [values, setValues] = useState({ username: '', password: '', confirm: '', full_name: '' })
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)
  const set = (name) => (e) => setValues((prev) => ({ ...prev, [name]: e.target.value }))

  const submit = async (e) => {
    e.preventDefault()
    if (setupRequired && values.password !== values.confirm) {
      setError(t('Le due password non coincidono.'))
      return
    }
    setBusy(true)
    setError(null)
    try {
      const result = setupRequired
        ? await api.post('/auth/setup', { username: values.username, password: values.password, full_name: values.full_name || null })
        : await api.post('/auth/login', { username: values.username, password: values.password })
      signedIn(result.user)
    } catch (err) {
      setError(err.message)
      setBusy(false)
    }
  }

  return (
    <div className="login">
      <form className="login__card" onSubmit={submit}>
        <p className="brand login__brand">
          <span className="brand__mark" aria-hidden="true">
            <span />
            <span />
          </span>
          NetMap
        </p>
        {setupRequired ? (
          <>
            <h1>{t("Crea l'amministratore")}</h1>
            <p className="page-intro">{t('È il primo accesso: scegli nome utente e password dell\'amministratore. Gli altri utenti li crei dopo, da "Utenti".')}</p>
          </>
        ) : (
          <h1>{t('Accedi')}</h1>
        )}
        <label className="field">
          <span className="field__label">{t('Nome utente')}</span>
          <input className="input" autoComplete="username" value={values.username} onChange={set('username')} required autoFocus />
          {directory && !setupRequired && <span className="hint">{t('Anche con il tuo utente di Windows, per esempio mario.rossi.')}</span>}
        </label>
        {setupRequired && (
          <label className="field">
            <span className="field__label">{t('Nome e cognome')}</span>
            <input className="input" autoComplete="name" value={values.full_name} onChange={set('full_name')} />
          </label>
        )}
        <label className="field">
          <span className="field__label">{t('Password')}</span>
          <input className="input" type="password" autoComplete={setupRequired ? 'new-password' : 'current-password'}
            value={values.password} onChange={set('password')} required minLength={setupRequired ? 8 : undefined} />
          {setupRequired && <span className="hint">{t('Almeno 8 caratteri.')}</span>}
        </label>
        {setupRequired && (
          <label className="field">
            <span className="field__label">{t('Ripeti la password')}</span>
            <input className="input" type="password" autoComplete="new-password" value={values.confirm} onChange={set('confirm')} required />
          </label>
        )}
        {error && <p className="form__error" role="alert">{error}</p>}
        <button type="submit" className="btn btn--primary" disabled={busy}>
          {busy ? t('Attendi…') : setupRequired ? t('Crea e accedi') : t('Accedi')}
        </button>
        <div className="login__lang" role="group" aria-label={t('Lingua')}>
          {LANGUAGES.map((option) => (
            <button key={option.value} type="button" className={`link-button${LANG === option.value ? ' is-current' : ''}`}
              aria-pressed={LANG === option.value} onClick={() => LANG !== option.value && setLang(option.value)}>
              {option.label}
            </button>
          ))}
        </div>
        <p className="login__version"><VersionLabel /></p>
      </form>
    </div>
  )
}
