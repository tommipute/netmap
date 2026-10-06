import { useState } from 'react'
import { api } from '../api'
import Modal from './Modal'

export default function PasswordDialog({ onClose }) {
  const [values, setValues] = useState({ current: '', next: '', confirm: '' })
  const [error, setError] = useState(null)
  const [done, setDone] = useState(false)
  const set = (name) => (e) => setValues((prev) => ({ ...prev, [name]: e.target.value }))

  const submit = async (e) => {
    e.preventDefault()
    if (values.next !== values.confirm) {
      setError('Le due password nuove non coincidono.')
      return
    }
    try {
      await api.post('/auth/password', { current_password: values.current, new_password: values.next })
      setDone(true)
    } catch (err) {
      setError(err.message)
    }
  }

  return (
    <Modal title="Cambia password" onClose={onClose}>
      {done ? (
        <div className="form">
          <p>Password cambiata. Le altre sessioni aperte con questo utente sono state chiuse.</p>
          <div className="modal__footer">
            <button type="button" className="btn btn--primary" onClick={onClose}>Chiudi</button>
          </div>
        </div>
      ) : (
        <form className="form" onSubmit={submit}>
          <div className="form__grid">
            <label className="field field--wide">
              <span className="field__label">Password attuale</span>
              <input className="input" type="password" autoComplete="current-password" value={values.current} onChange={set('current')} required />
            </label>
            <label className="field">
              <span className="field__label">Nuova password</span>
              <input className="input" type="password" autoComplete="new-password" minLength={8} value={values.next} onChange={set('next')} required />
              <span className="hint">Almeno 8 caratteri.</span>
            </label>
            <label className="field">
              <span className="field__label">Ripeti la nuova password</span>
              <input className="input" type="password" autoComplete="new-password" value={values.confirm} onChange={set('confirm')} required />
            </label>
          </div>
          {error && <p className="form__error" role="alert">{error}</p>}
          <div className="modal__footer">
            <button type="button" className="btn btn--ghost" onClick={onClose}>Annulla</button>
            <button type="submit" className="btn btn--primary">Cambia password</button>
          </div>
        </form>
      )}
    </Modal>
  )
}
