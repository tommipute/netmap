import { useState } from 'react'
import { api } from '../api'
import { useAuth } from '../auth'

/** Accesso; al primo avvio (nessun utente) crea l'amministratore. */
export default function LoginPage() {
  const { setupRequired, signedIn } = useAuth()
  const [values, setValues] = useState({ username: '', password: '', confirm: '', full_name: '' })
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)
  const set = (name) => (e) => setValues((prev) => ({ ...prev, [name]: e.target.value }))

  const submit = async (e) => {
    e.preventDefault()
    if (setupRequired && values.password !== values.confirm) {
      setError('Le due password non coincidono.')
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
            <h1>Crea l'amministratore</h1>
            <p className="page-intro">È il primo accesso: scegli nome utente e password dell'amministratore. Gli altri utenti li crei dopo, da "Utenti".</p>
          </>
        ) : (
          <h1>Accedi</h1>
        )}
        <label className="field">
          <span className="field__label">Nome utente</span>
          <input className="input" autoComplete="username" value={values.username} onChange={set('username')} required autoFocus />
        </label>
        {setupRequired && (
          <label className="field">
            <span className="field__label">Nome e cognome</span>
            <input className="input" autoComplete="name" value={values.full_name} onChange={set('full_name')} />
          </label>
        )}
        <label className="field">
          <span className="field__label">Password</span>
          <input className="input" type="password" autoComplete={setupRequired ? 'new-password' : 'current-password'}
            value={values.password} onChange={set('password')} required minLength={setupRequired ? 8 : undefined} />
          {setupRequired && <span className="hint">Almeno 8 caratteri.</span>}
        </label>
        {setupRequired && (
          <label className="field">
            <span className="field__label">Ripeti la password</span>
            <input className="input" type="password" autoComplete="new-password" value={values.confirm} onChange={set('confirm')} required />
          </label>
        )}
        {error && <p className="form__error" role="alert">{error}</p>}
        <button type="submit" className="btn btn--primary" disabled={busy}>
          {busy ? 'Attendi…' : setupRequired ? 'Crea e accedi' : 'Accedi'}
        </button>
      </form>
    </div>
  )
}
