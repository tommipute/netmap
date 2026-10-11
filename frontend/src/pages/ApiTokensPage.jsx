import { useState } from 'react'
import { api } from '../api'
import { ROLES, useAuth } from '../auth'
import { ErrorBox, Loading } from '../components/Bits'
import { IconButton } from '../components/Icon'
import Modal from '../components/Modal'
import { useApi, useOptions } from '../hooks'
import { formatDateTime, labelOf } from '../options'
import { t, tc } from '../i18n'

const EXPIRY = [
  { value: '', label: t('Mai') },
  { value: '30', label: t('Tra 30 giorni') },
  { value: '90', label: t('Tra 90 giorni') },
  { value: '365', label: t('Tra un anno') },
]

/** Crea un token: il testo intero si vede solo qui, una volta. */
function NewTokenDialog({ onClose, onCreated }) {
  const { isAdmin, user } = useAuth()
  const users = useOptions(isAdmin ? 'users' : null)
  const [values, setValues] = useState({ name: '', read_only: false, expires_days: '', user_id: '', description: '' })
  const [error, setError] = useState(null)
  const [created, setCreated] = useState(null)
  const [copied, setCopied] = useState(false)
  const set = (name, value) => setValues((prev) => ({ ...prev, [name]: value }))

  const submit = async (e) => {
    e.preventDefault()
    e.stopPropagation()
    try {
      const row = await api.post('/api-tokens', {
        name: values.name.trim(),
        read_only: values.read_only,
        expires_days: values.expires_days ? Number(values.expires_days) : null,
        user_id: values.user_id ? Number(values.user_id) : null,
        description: values.description.trim() || null,
      })
      setCreated(row)
      onCreated()
    } catch (err) {
      setError(err.message)
    }
  }

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(created.token)
      setCopied(true)
    } catch {
      setCopied(false)
    }
  }

  if (created) {
    return (
      <Modal title={t('Token creato')} onClose={onClose}>
        <div className="form">
          <p>{t('Copia il token adesso: non si potrà più vedere. Se lo perdi, revocalo e creane un altro.')}</p>
          <div className="token-box">
            <code className="mono" data-testid="new-token">{created.token}</code>
            <IconButton icon={copied ? 'check' : 'copy'} label={copied ? t('Copiato') : t('Copia il token')} small onClick={copy} />
          </div>
          {copied && <p className="hint">{t('Copiato')}</p>}
          <p className="hint">{t('Si usa nell\'intestazione Authorization di ogni richiesta:')}</p>
          <pre className="token-example">{`curl -H "Authorization: Bearer ${created.token}" \\\n  ${window.location.origin}/api/devices?limit=10`}</pre>
          <div className="modal__footer">
            <button type="button" className="btn btn--primary" onClick={onClose}>{t('Chiudi')}</button>
          </div>
        </div>
      </Modal>
    )
  }

  return (
    <Modal title={t('Nuovo token API')} onClose={onClose}>
      <form className="form" onSubmit={submit}>
        <div className="form__grid">
          <label className="field field--wide">
            <span className="field__label">{t('Nome')}<span className="field__req" aria-hidden="true"> *</span></span>
            <input className="input" value={values.name} onChange={(e) => set('name', e.target.value)} placeholder={t('Script inventario')} required maxLength={100} />
            <span className="hint">{t('Per riconoscerlo: chi lo usa e per cosa.')}</span>
          </label>
          {isAdmin && (
            <label className="field">
              <span className="field__label">{t('Utente')}</span>
              <select className="input" value={values.user_id} onChange={(e) => set('user_id', e.target.value)}>
                <option value="">{t('Io ({name})', { name: user?.username || '' })}</option>
                {users.filter((u) => u.active && u.id !== user?.id).map((u) => (
                  <option key={u.id} value={u.id}>{u.username} · {labelOf(ROLES, u.role)}</option>
                ))}
              </select>
              <span className="hint">{t('Il token può fare solo quello che può fare il suo utente. Per un programma conviene un utente apposta.')}</span>
            </label>
          )}
          <label className="field">
            <span className="field__label">{t('Scadenza')}</span>
            <select className="input" value={values.expires_days} onChange={(e) => set('expires_days', e.target.value)}>
              {EXPIRY.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
            </select>
          </label>
          <div className="field field--wide">
            <label className="check">
              <input type="checkbox" checked={values.read_only} onChange={(e) => set('read_only', e.target.checked)} />
              {t('Solo lettura (anche se l\'utente può modificare)')}
            </label>
          </div>
          <label className="field field--wide">
            <span className="field__label">{t('Descrizione')}</span>
            <textarea className="input" rows={2} value={values.description} onChange={(e) => set('description', e.target.value)} />
          </label>
        </div>
        {error && <p className="form__error" role="alert">{error}</p>}
        <div className="modal__footer">
          <button type="button" className="btn btn--ghost" onClick={onClose}>{t('Annulla')}</button>
          <button type="submit" className="btn btn--primary">{t('Crea token')}</button>
        </div>
      </form>
    </Modal>
  )
}

export default function ApiTokensPage() {
  const { isAdmin } = useAuth()
  const { data, error, loading, reload } = useApi('/api-tokens')
  const [dialog, setDialog] = useState(false)
  const [actionError, setActionError] = useState(null)

  const revoke = async (row) => {
    if (!window.confirm(t('Revocare il token "{name}"? I programmi che lo usano non potranno più accedere.', { name: row.name }))) return
    try {
      await api.del(`/api-tokens/${row.id}`)
      setActionError(null)
      reload()
    } catch (err) {
      setActionError(err)
    }
  }

  return (
    <div className="page">
      <header className="page-head">
        <div>
          <h1>{tc('elenco', 'Token API')}</h1>
          <p className="page-intro">
            {t('Chiavi per gli script e gli altri programmi che leggono o modificano NetMap con le API (documentazione nel menu utente). Ogni token agisce come il suo utente e mai con più permessi; le modifiche fatte con un token compaiono nello storico con l\'origine "API". Cambiare la password dell\'utente o disattivarlo revoca i suoi token.')}
          </p>
        </div>
        <div className="page-head__actions">
          <IconButton icon="plus" label={t('Nuovo token API')} className="btn--primary" onClick={() => setDialog(true)} />
        </div>
      </header>
      <ErrorBox error={error || actionError} />
      {loading && !data ? <Loading /> : data && (
        data.length === 0 ? <p className="muted">{t('Nessun token API.')}</p> : (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>{t('Nome')}</th>
                  <th>{t('Token')}</th>
                  {isAdmin && <th>{t('Utente')}</th>}
                  <th>{t('Permessi')}</th>
                  <th>{t('Scadenza')}</th>
                  <th>{t('Ultimo uso')}</th>
                  <th>{t('Creato')}</th>
                  <th aria-label={t('Azioni')} />
                </tr>
              </thead>
              <tbody>
                {data.map((row) => (
                  <tr key={row.id}>
                    <td><strong>{row.name}</strong>{row.description && <div className="hint">{row.description}</div>}</td>
                    <td className="mono">{row.prefix}…</td>
                    {isAdmin && <td>{row.username}</td>}
                    <td>{row.read_only ? t('Solo lettura') : labelOf(ROLES, row.user_role)}</td>
                    <td>
                      {row.expired ? <span className="live live--down">{t('Scaduto')}</span> : row.expires_at ? formatDateTime(row.expires_at) : <span className="muted">{t('Mai')}</span>}
                    </td>
                    <td>
                      {row.last_used_at ? <>{formatDateTime(row.last_used_at)}<div className="hint mono">{row.last_used_ip}</div></> : <span className="muted">{t('Mai usato')}</span>}
                    </td>
                    <td>{formatDateTime(row.created_at)}</td>
                    <td className="table__actions">
                      <IconButton icon="trash" label={t('Revoca')} small danger onClick={() => revoke(row)} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )
      )}
      {dialog && <NewTokenDialog onClose={() => setDialog(false)} onCreated={reload} />}
    </div>
  )
}
