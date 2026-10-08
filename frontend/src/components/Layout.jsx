import { useEffect, useRef, useState } from 'react'
import { Link, NavLink, Outlet, useNavigate } from 'react-router-dom'
import { ROLES, useAuth } from '../auth'
import { usePendingCount, useStatusSummary } from '../hooks'
import { labelOf } from '../options'
import { NAV, resources } from '../resources'
import { useTheme } from '../theme'
import PasswordDialog from './PasswordDialog'
import { Icon } from './Icon'
import { LANG, LANGUAGES, setLang, t } from '../i18n'
import { VERSION } from '../version'

const THEMES = [
  { value: 'system', label: t('Automatico') },
  { value: 'light', label: t('Chiaro') },
  { value: 'dark', label: t('Scuro') },
]
const ROLE_HELP = {
  viewer: t('Consulta tutto, senza modificare.'),
  editor: t('Modifica i dati e approva le modifiche della scansione.'),
  admin: t('Tutto, compresi utenti e avvisi.'),
}

/** Stato live: solo pallini e numeri (verde = rispondono, rosso = non rispondono), ognuno porta all'elenco. */
function StatusChip() {
  const summary = useStatusSummary()
  if (!summary || summary.up + summary.down === 0) return null
  return (
    <span className="live-chip" aria-label={t('Stato live dei device con IP di management')}>
      <Link to="/devices?reachable=true" className="live-chip__item" title={t('{n} rispondono', { n: summary.up })}>
        <span className="live-dot live-dot--up" />{summary.up}
      </Link>
      <Link to="/devices?reachable=false" className={`live-chip__item${summary.down ? ' live-chip__item--down' : ''}`}
        title={t('{n} non rispondono', { n: summary.down })}>
        <span className="live-dot live-dot--down" />{summary.down}
      </Link>
    </span>
  )
}

const initials = (name) =>
  name.split(/[\s._-]+/).filter(Boolean).slice(0, 2).map((w) => w[0].toUpperCase()).join('') || '?'

/** Utente in alto a destra: menu con ruolo, tema chiaro/scuro, password, documentazione API, esci. */
function UserMenu() {
  const { enabled, user, logout } = useAuth()
  const [theme, setTheme] = useTheme()
  const [open, setOpen] = useState(false)
  const [dialog, setDialog] = useState(false)
  const boxRef = useRef(null)
  useEffect(() => {
    if (!open) return undefined
    const close = (e) => !boxRef.current?.contains(e.target) && setOpen(false)
    const esc = (e) => e.key === 'Escape' && setOpen(false)
    document.addEventListener('mousedown', close)
    document.addEventListener('keydown', esc)
    return () => {
      document.removeEventListener('mousedown', close)
      document.removeEventListener('keydown', esc)
    }
  }, [open])

  const signedIn = enabled && user
  const name = signedIn ? user.full_name || user.username : t('Impostazioni')
  return (
    <div className="user-menu" ref={boxRef}>
      <button type="button" className="user-menu__button" aria-haspopup="menu" aria-expanded={open}
        onClick={() => setOpen((v) => !v)} title={signedIn ? `${name} · ${labelOf(ROLES, user.role)}` : t('Impostazioni')}>
        <span className="user-menu__avatar" aria-hidden="true">{signedIn ? initials(name) : <Icon name="user" />}</span>
        {signedIn && <span className="user-menu__name">{name}</span>}
        <Icon name="down" size={14} />
      </button>
      {open && (
        <div className="user-menu__panel" role="menu">
          {signedIn && (
            <div className="user-menu__head">
              <strong>{name}</strong>
              <span className="muted">{user.username}</span> <span className="tag">{labelOf(ROLES, user.role)}</span>
              <p className="hint">{ROLE_HELP[user.role]}</p>
            </div>
          )}
          <div className="user-menu__section">
            <span className="hint">{t('Tema')}</span>
            <div className="segmented" role="group" aria-label={t('Tema')}>
              {THEMES.map((option) => (
                <button key={option.value} type="button" className={`segmented__item${theme === option.value ? ' segmented__item--on' : ''}`}
                  aria-pressed={theme === option.value} onClick={() => setTheme(option.value)}>
                  {option.label}
                </button>
              ))}
            </div>
          </div>
          <div className="user-menu__section">
            <span className="hint">{t('Lingua')}</span>
            <div className="segmented" role="group" aria-label={t('Lingua')}>
              {LANGUAGES.map((option) => (
                <button key={option.value} type="button" className={`segmented__item${LANG === option.value ? ' segmented__item--on' : ''}`}
                  aria-pressed={LANG === option.value} onClick={() => LANG !== option.value && setLang(option.value)}>
                  {option.label}
                </button>
              ))}
            </div>
          </div>
          <div className="user-menu__sep" />
          {signedIn && (
            <button type="button" role="menuitem" className="user-menu__item" onClick={() => { setOpen(false); setDialog(true) }}>
              <Icon name="key" /> {t('Cambia password')}
            </button>
          )}
          <a role="menuitem" className="user-menu__item" href="/docs" target="_blank" rel="noreferrer" onClick={() => setOpen(false)}>
            <Icon name="open" /> {t('Documentazione API')}
          </a>
          {signedIn && (
            <>
              <div className="user-menu__sep" />
              <button type="button" role="menuitem" className="user-menu__item user-menu__item--danger" onClick={logout}>
                <Icon name="logout" /> {t('Esci')}
              </button>
            </>
          )}
        </div>
      )}
      {dialog && <PasswordDialog onClose={() => setDialog(false)} />}
    </div>
  )
}

export default function Layout() {
  const navigate = useNavigate()
  const { isAdmin } = useAuth()
  const [query, setQuery] = useState('')
  const badges = { pending: usePendingCount() }

  const search = (e) => {
    e.preventDefault()
    const q = query.trim()
    if (q.length >= 2) navigate(`/search?q=${encodeURIComponent(q)}`)
  }

  return (
    <div className="shell">
      <aside className="sidebar">
        <NavLink to="/" className="brand" aria-label={t('NetMap, vai alle mappe')}>
          <span className="brand__mark" aria-hidden="true">
            <span />
            <span />
          </span>
          NetMap
        </NavLink>
        <nav aria-label={t('Sezioni')}>
          {NAV.filter((group) => !group.admin || isAdmin).map((group) => (
            <div key={group.title} className="nav-group">
              <p className="nav-group__title">{group.title}</p>
              {group.items.map((item) => {
                const { to, title, badge } = typeof item === 'string' ? { to: resources[item].path, title: resources[item].title } : item
                const count = badge ? badges[badge] : 0
                return (
                  <NavLink key={to} to={`/${to}`} className="nav-link">
                    {title}
                    {count > 0 && (
                      <span className="nav-badge" aria-label={t('{n} in attesa', { n: count })}>
                        {count > 999 ? '999+' : count}
                      </span>
                    )}
                  </NavLink>
                )
              })}
            </div>
          ))}
        </nav>
      </aside>
      <div className="main">
        <header className="topbar">
          <form className="topbar__search" role="search" onSubmit={search}>
            <input
              type="search"
              className="input"
              placeholder={t('Cerca device, IP o MAC address')}
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              aria-label={t('Cerca device, IP o MAC address')}
            />
          </form>
          <StatusChip />
          <span className="topbar__spacer" />
          <UserMenu />
        </header>
        <main className="content">
          <Outlet />
        </main>
        <footer className="appfoot no-print">NetMap {VERSION}</footer>
      </div>
    </div>
  )
}
