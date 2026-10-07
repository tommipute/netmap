/**
 * Tema dell'interfaccia: 'system' (segue il sistema operativo), 'light' o 'dark'. Scelta di chi guarda, salvata
 * nel browser. Il CSS usa :root[data-theme] (vedi styles.css); index.html la applica prima del primo disegno.
 */
import { useEffect, useState } from 'react'

const KEY = 'netmap.theme'
const listeners = new Set()

export function getTheme() {
  try {
    const value = localStorage.getItem(KEY)
    return value === 'light' || value === 'dark' ? value : 'system'
  } catch {
    return 'system'
  }
}

function apply(theme) {
  const root = document.documentElement
  if (theme === 'system') delete root.dataset.theme
  else root.dataset.theme = theme
}

export function setTheme(theme) {
  try {
    if (theme === 'system') localStorage.removeItem(KEY)
    else localStorage.setItem(KEY, theme)
  } catch {
    // senza storage la scelta vale finché la pagina resta aperta
  }
  apply(theme)
  listeners.forEach((fn) => fn(theme))
}

/** [tema scelto, cambia tema]; React Flow vuole 'system' | 'light' | 'dark', gli stessi valori. */
export function useTheme() {
  const [theme, setLocal] = useState(getTheme)
  useEffect(() => {
    listeners.add(setLocal)
    return () => listeners.delete(setLocal)
  }, [])
  return [theme, setTheme]
}
