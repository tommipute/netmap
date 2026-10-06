import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import { api } from './api'

/** Utente collegato e permessi. Con il login disattivato nel backend tutto è permesso. */
const AuthContext = createContext(null)

const WRITE_ROLES = ['admin', 'editor']

export const ROLES = [
  { value: 'viewer', label: 'Solo lettura' },
  { value: 'editor', label: 'Modifica' },
  { value: 'admin', label: 'Amministratore' },
]

export function AuthProvider({ children }) {
  const [state, setState] = useState({ loading: true, enabled: true, setupRequired: false, user: null, error: null })

  const refresh = useCallback(async () => {
    try {
      const status = await api.get('/auth/status')
      if (!status.auth_enabled) {
        setState({ loading: false, enabled: false, setupRequired: false, user: null, error: null })
        return
      }
      let user = null
      if (!status.setup_required) user = await api.get('/auth/me').catch(() => null)
      setState({ loading: false, enabled: true, setupRequired: status.setup_required, user, error: null })
    } catch (error) {
      setState((prev) => ({ ...prev, loading: false, error }))
    }
  }, [])

  useEffect(() => {
    refresh()
  }, [refresh])

  useEffect(() => {
    const expired = () => setState((prev) => (prev.enabled ? { ...prev, user: null } : prev))
    window.addEventListener('netmap:unauthorized', expired)
    return () => window.removeEventListener('netmap:unauthorized', expired)
  }, [])

  const value = useMemo(() => {
    const role = state.user?.role
    return {
      ...state,
      canEdit: !state.enabled || WRITE_ROLES.includes(role),
      isAdmin: !state.enabled || role === 'admin',
      signedIn: (user) => setState((prev) => ({ ...prev, user, setupRequired: false })),
      logout: async () => {
        await api.post('/auth/logout').catch(() => {})
        setState((prev) => ({ ...prev, user: null }))
      },
      refresh,
    }
  }, [state, refresh])

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  return useContext(AuthContext)
}
