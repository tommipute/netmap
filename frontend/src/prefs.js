/**
 * Preferenze di chi guarda (dialogo Preferenze del menu utente), oltre a tema e lingua: menu, elenchi, date, mappa,
 * stato live. Ognuna ha un valore di default e un elenco di valori ammessi: un valore vecchio o sbagliato torna al
 * default. Salvate con store(): nel browser e, per l'utente collegato, sul server.
 */
import { useEffect, useState } from 'react'
import { applyDocument, readLocal, store } from './storage'

const ON_OFF = ['1', '0']

export const PREFS = {
  menu: { key: 'netmap.menu', default: 'side', values: ['side', 'top'] },
  menuSections: { key: 'netmap.menuSections', default: 'one', values: ['one', 'all'] },
  density: { key: 'netmap.density', default: 'normal', values: ['normal', 'compact'] },
  pageSize: { key: 'netmap.pageSize', default: '50', values: ['25', '50', '100', '200'] },
  start: { key: 'netmap.start', default: 'maps' }, // percorso senza "/" (deve esistere nel menu)
  dates: { key: 'netmap.dates', default: 'full', values: ['full', 'relative'] },
  clock: { key: 'netmap.clock', default: '24', values: ['24', '12'] },
  refresh: { key: 'netmap.refresh', default: '30', values: ['15', '30', '60', '300', '0'] }, // secondi, 0 = mai
  // Caselle della mappa all'apertura; con mapRemember la mappa ricorda l'ultima scelta (sono le stesse chiavi)
  mapLocations: { key: 'netmap.map.locations', default: '1', values: ON_OFF },
  mapEndpoints: { key: 'netmap.map.endpoints', default: '1', values: ON_OFF },
  mapBackground: { key: 'netmap.map.background', default: '1', values: ON_OFF },
  mapRemember: { key: 'netmap.map.remember', default: '1', values: ON_OFF },
}

const listeners = new Set()

export function getPref(name) {
  const pref = PREFS[name]
  const value = readLocal(pref.key)
  return value && (!pref.values || pref.values.includes(value)) ? value : pref.default
}

export function setPref(name, value) {
  const pref = PREFS[name]
  store(pref.key, value === pref.default ? null : value)
  if (name === 'density') applyDocument()
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

/** Ogni quanti millisecondi si aggiorna lo stato live (0 = mai). */
export const refreshMs = (value) => Number(value) * 1000
