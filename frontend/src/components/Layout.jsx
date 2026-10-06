import { useState } from 'react'
import { Link, NavLink, Outlet, useNavigate } from 'react-router-dom'
import { ROLES, useAuth } from '../auth'
import { usePendingCount, useStatusSummary } from '../hooks'
import { labelOf } from '../options'
import { NAV, resources } from '../resources'
import PasswordDialog from './PasswordDialog'
import { IconButton } from './Icon'

function StatusChip() {
  const summary = useStatusSummary()
  if (!summary || summary.up + summary.down === 0) return null
  return (
    <Link to="/devices?reachable=false" className="live-chip" title="Stato live dei device con IP di management">
      <span className="live-chip__item"><span className="live-dot live-dot--up" />{summary.up}</span>
      <span className={`live-chip__item${summary.down ? ' live-chip__item--down' : ''}`}>
        <span className="live-dot live-dot--down" />{summary.down} non rispondono
      </span>
    </Link>
  )
}

function UserMenu() {
  const { enabled, user, logout } = useAuth()
  const [dialog, setDialog] = useState(false)
  if (!enabled || !user) return null
  return (
    <div className="user-menu">
      <span className="user-menu__name" title={labelOf(ROLES, user.role)}>
        {user.full_name || user.username}
        <span className="tag">{labelOf(ROLES, user.role)}</span>
      </span>
      <IconButton icon="key" label="Cambia password" small className="btn--ghost" onClick={() => setDialog(true)} />
      <IconButton icon="logout" label="Esci" small className="btn--ghost" onClick={logout} />
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
        <NavLink to="/" className="brand" aria-label="NetMap, vai alle mappe">
          <span className="brand__mark" aria-hidden="true">
            <span />
            <span />
          </span>
          NetMap
        </NavLink>
        <nav aria-label="Sezioni">
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
                      <span className="nav-badge" aria-label={`${count} in attesa`}>
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
              placeholder="Cerca device, IP o MAC address"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              aria-label="Cerca device, IP o MAC address"
            />
          </form>
          <StatusChip />
          <a className="topbar__link" href="/docs" target="_blank" rel="noreferrer">
            API
          </a>
          <UserMenu />
        </header>
        <main className="content">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
