/**
 * Tema dell'interfaccia: 'system' (segue il sistema operativo), 'light' o 'dark'. Scelta di chi guarda, salvata
 * nel browser. Il CSS usa :root[data-theme] (vedi styles.css); index.html la applica prima del primo disegno.
 */
import { useEffect, useState } from 'react'
import { applyDocument, readLocal, store } from './storage'

const KEY = 'netmap.theme'
const listeners = new Set()

export function getTheme() {
  const value = readLocal(KEY)
  return value === 'light' || value === 'dark' ? value : 'system'
}

export function setTheme(theme) {
  store(KEY, theme === 'system' ? null : theme)
  applyDocument()
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
