import { useState } from 'react'
import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { usePendingCount } from '../hooks'
import { NAV, resources } from '../resources'

export default function Layout() {
  const navigate = useNavigate()
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
          {NAV.map((group) => (
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
          <a className="topbar__link" href="/docs" target="_blank" rel="noreferrer">
            API
          </a>
        </header>
        <main className="content">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
