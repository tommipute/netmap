/**
 * Preferenze di chi guarda, salvate nel browser (come tema e lingua): posizione del menu, righe per pagina, pagina
 * iniziale. Ognuna ha un valore di default e un elenco di valori ammessi: un valore vecchio o sbagliato torna al default.
 */
import { useEffect, useState } from 'react'

export const PREFS = {
  menu: { key: 'netmap.menu', default: 'side', values: ['side', 'top'] },
  pageSize: { key: 'netmap.pageSize', default: '50', values: ['25', '50', '100', '200'] },
  start: { key: 'netmap.start', default: 'maps' }, // percorso senza "/" (deve esistere nel menu)
}

const listeners = new Set()

export function getPref(name) {
  const pref = PREFS[name]
  try {
    const value = localStorage.getItem(pref.key)
    if (value && (!pref.values || pref.values.includes(value))) return value
  } catch {
    // senza storage valgono i default
  }
  return pref.default
}

export function setPref(name, value) {
  const pref = PREFS[name]
  try {
    if (value === pref.default) localStorage.removeItem(pref.key)
    else localStorage.setItem(pref.key, value)
  } catch {
    // senza storage la scelta vale finché la pagina resta aperta
  }
  listeners.forEach((fn) => fn(name, value))
}

/** [valore, cambia valore], aggiornato in tutte le parti della pagina che la usano. */
export function usePref(name) {
  const [value, setLocal] = useState(() => getPref(name))
  useEffect(() => {
    const fn = (changed, next) => changed === name && setLocal(next)
    listeners.add(fn)
    return () => listeners.delete(fn)
  }, [name])
  return [value, (next) => setPref(name, next)]
}
