import { useEffect, useRef, useState } from 'react'
import { Link, NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { ROLES, useAuth } from '../auth'
import { usePendingCount, useStatusSummary, useVersion } from '../hooks'
import { labelOf } from '../options'
import { usePref } from '../prefs'
import { navGroupOf, navGroups, navItem } from '../resources'
import PasswordDialog from './PasswordDialog'
import PrefsDialog from './PrefsDialog'
import { Icon } from './Icon'
import { LANG, t, tc } from '../i18n'
import VersionLabel, { repoFileUrl } from './VersionLabel'

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

/** Utente in alto a destra: menu con ruolo, preferenze, password, manuale, documentazione API, esci. */
function UserMenu() {
  const { enabled, user, logout } = useAuth()
  const version = useVersion()
  const [open, setOpen] = useState(false)
  const [dialog, setDialog] = useState(false)
  const [prefs, setPrefs] = useState(false)
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
              {user.source === 'ad' && <p className="hint">{t('Utente di dominio: password e ruolo vengono da Active Directory.')}</p>}
            </div>
          )}
          <button type="button" role="menuitem" className="user-menu__item" onClick={() => { setOpen(false); setPrefs(true) }}>
            <Icon name="sliders" /> {t('Preferenze')}
          </button>
          <div className="user-menu__sep" />
          {signedIn && user.source !== 'ad' && (
            <button type="button" role="menuitem" className="user-menu__item" onClick={() => { setOpen(false); setDialog(true) }}>
              <Icon name="key" /> {t('Cambia password')}
            </button>
          )}
          <a role="menuitem" className="user-menu__item" href={repoFileUrl(version, LANG === 'en' ? 'docs/manual.md' : 'docs/manuale.md')}
            target="_blank" rel="noreferrer" onClick={() => setOpen(false)}>
            <Icon name="book" /> {t('Manuale')}
          </a>
          {signedIn && (
            <Link role="menuitem" className="user-menu__item" to="/api-tokens" onClick={() => setOpen(false)}>
              <Icon name="key" /> {tc('elenco', 'Token API')}
            </Link>
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
      {prefs && <PrefsDialog onClose={() => setPrefs(false)} />}
    </div>
  )
}

const NARROW = '(max-width: 860px)'

/** Schermo stretto (telefono): il menu sta sempre in alto. */
function useNarrow() {
  const [narrow, setNarrow] = useState(() => window.matchMedia(NARROW).matches)
  useEffect(() => {
    const query = window.matchMedia(NARROW)
    const change = () => setNarrow(query.matches)
    query.addEventListener('change', change)
    return () => query.removeEventListener('change', change)
  }, [])
  return narrow
}

const Badge = ({ count }) => count > 0 && (
  <span className="nav-badge" aria-label={t('{n} in attesa', { n: count })}>{count > 999 ? '999+' : count}</span>
)

/** Voci di un gruppo: link alle pagine, con il numero in attesa dove serve. */
function NavItems({ group, badges, onPick }) {
  return group.items.map(navItem).map(({ to, title, badge }) => (
    <NavLink key={to} to={`/${to}`} className="nav-link" onClick={onPick}>
      {title}
      <Badge count={badge ? badges[badge] : 0} />
    </NavLink>
  ))
}

const groupCount = (group, badges) => group.items.map(navItem).reduce((n, item) => n + (item.badge ? badges[item.badge] || 0 : 0), 0)

const Brand = () => (
  <NavLink to="/" className="brand" aria-label={t('NetMap, vai alla pagina iniziale')}>
    <span className="brand__mark" aria-hidden="true">
      <span />
      <span />
    </span>
    NetMap
  </NavLink>
)

/** Menu a lato: solo i nomi delle sezioni; un clic apre o chiude la sezione. Di solito una alla volta, e quella
 * della pagina aperta si apre da sola; con "tutte aperte" nelle preferenze ognuna si chiude per conto suo. */
function SideNav({ groups, badges }) {
  const { pathname } = useLocation()
  const [sections] = usePref('menuSections')
  const all = sections === 'all'
  const current = navGroupOf(groups, pathname)?.title
  const [open, setOpen] = useState(current) // una alla volta: quella aperta
  const [closed, setClosed] = useState(() => new Set()) // tutte aperte: quelle chiuse
  useEffect(() => {
    if (current) setOpen(current)
  }, [current])
  const isOpen = (title) => (all ? !closed.has(title) : open === title)
  const toggle = (title) => {
    if (!all) return setOpen(open === title ? null : title)
    return setClosed((prev) => {
      const next = new Set(prev)
      if (!next.delete(title)) next.add(title)
      return next
    })
  }

  return (
    <aside className="sidebar">
      <Brand />
      <nav aria-label={t('Sezioni')}>
        {groups.map((group) => {
          const expanded = isOpen(group.title)
          return (
            <div key={group.title} className={`nav-group${expanded ? ' nav-group--open' : ''}`}>
              <button type="button" className="nav-group__title"
                aria-expanded={expanded} onClick={() => toggle(group.title)}>
                <span>{group.title}</span>
                {!expanded && <Badge count={groupCount(group, badges)} />}
                <Icon name={expanded ? 'up' : 'down'} size={14} />
              </button>
              {expanded && <div className="nav-group__items"><NavItems group={group} badges={badges} /></div>}
            </div>
          )
        })}
      </nav>
    </aside>
  )
}

/** Menu in alto: i nomi delle sezioni in una barra; un clic apre la tendina con le pagine. */
function TopNav({ groups, badges }) {
  const { pathname } = useLocation()
  const current = navGroupOf(groups, pathname)?.title
  const [open, setOpen] = useState(null)
  const [left, setLeft] = useState(0)
  const boxRef = useRef(null)
  const panelRef = useRef(null)

  useEffect(() => setOpen(null), [pathname])
  useEffect(() => {
    if (!open) return undefined
    const close = (e) => !boxRef.current?.contains(e.target) && setOpen(null)
    const esc = (e) => e.key === 'Escape' && setOpen(null)
    document.addEventListener('mousedown', close)
    document.addEventListener('keydown', esc)
    return () => {
      document.removeEventListener('mousedown', close)
      document.removeEventListener('keydown', esc)
    }
  }, [open])
  // La tendina resta dentro lo schermo anche sotto le ultime sezioni
  useEffect(() => {
    if (!open || !panelRef.current || !boxRef.current) return
    const box = boxRef.current.getBoundingClientRect()
    const max = box.width - panelRef.current.offsetWidth - 8
    setLeft((l) => Math.max(8, Math.min(l, max)))
  }, [open])

  const toggle = (e, title) => {
    if (open === title) return setOpen(null)
    const box = boxRef.current.getBoundingClientRect()
    setLeft(e.currentTarget.getBoundingClientRect().left - box.left)
    return setOpen(title)
  }
  const group = groups.find((g) => g.title === open)

  return (
    <header className="topnav" ref={boxRef}>
      <Brand />
      <nav className="topnav__groups" aria-label={t('Sezioni')}>
        {groups.map((g) => (
          <button key={g.title} type="button" aria-expanded={open === g.title} aria-haspopup="true"
            className={`topnav__group${current === g.title ? ' topnav__group--current' : ''}`} onClick={(e) => toggle(e, g.title)}>
            {g.title}
            <Badge count={groupCount(g, badges)} />
            <Icon name="down" size={14} />
          </button>
        ))}
      </nav>
      {group && (
        <div className="topnav__panel" ref={panelRef} style={{ left }}>
          <NavItems group={group} badges={badges} onPick={() => setOpen(null)} />
        </div>
      )}
    </header>
  )
}

export default function Layout() {
  const navigate = useNavigate()
  const { isAdmin } = useAuth()
  const [menu] = usePref('menu')
  const [dates] = usePref('dates')
  const [clock] = usePref('clock')
  const narrow = useNarrow()
  const [query, setQuery] = useState('')
  const badges = { pending: usePendingCount() }
  const groups = navGroups(isAdmin)
  const top = narrow || menu === 'top'

  const search = (e) => {
    e.preventDefault()
    const q = query.trim()
    if (q.length >= 2) navigate(`/search?q=${encodeURIComponent(q)}`)
  }

  return (
    <div className={`shell${top ? ' shell--top' : ''}`}>
      {top ? <TopNav groups={groups} badges={badges} /> : <SideNav groups={groups} badges={badges} />}
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
        {/* Cambiando il formato delle date la pagina si ridisegna */}
        <main className="content" key={`${dates}-${clock}`}>
          <Outlet />
        </main>
        <footer className="appfoot no-print"><VersionLabel /></footer>
      </div>
    </div>
  )
}
