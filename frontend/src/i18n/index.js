/**
 * Lingua dell'interfaccia: italiano (predefinita) o inglese, scelta nel menu utente o nella pagina di accesso e
 * salvata nel browser (localStorage `netmap.lang`). Cambiandola la pagina si ricarica: così anche le costanti dei
 * moduli (resources.jsx, options.js) si ricalcolano nella lingua nuova.
 *
 * Il testo italiano è la chiave: t('Salva modifiche') -> "Save changes" (dizionario in en.js). Una frase senza
 * traduzione resta in italiano. Variabili tra graffe: t('{n} elementi', { n: 3 }).
 * tServer() traduce i testi che arrivano dal server (errori, riepiloghi della scansione, nomi dei campi nello
 * storico): frase esatta oppure uno dei modelli (patterns) di en.js.
 */
import en from './en'

const KEY = 'netmap.lang'

export const LANGUAGES = [
  { value: 'it', label: 'Italiano' },
  { value: 'en', label: 'English' },
]

function read() {
  try {
    return localStorage.getItem(KEY) === 'en' ? 'en' : 'it'
  } catch {
    return 'it'
  }
}

export const LANG = read()
export const LOCALE = LANG === 'en' ? 'en-GB' : 'it-IT'
if (typeof document !== 'undefined') document.documentElement.lang = LANG

export function setLang(lang) {
  try {
    localStorage.setItem(KEY, lang)
  } catch {
    // senza storage la scelta non resta: si ricarica comunque
  }
  window.location.reload()
}

// Frasi senza traduzione viste durante l'uso (solo in sviluppo): servono a trovare quelle mancanti
const missing = new Set()
if (typeof window !== 'undefined' && import.meta.env?.DEV) window.__netmapMissing = missing

const fill = (text, vars) => (vars ? text.replace(/\{(\w+)\}/g, (m, k) => (k in vars ? vars[k] : m)) : text)

export function t(text, vars) {
  if (LANG === 'it' || typeof text !== 'string') return fill(text, vars)
  const translated = en.strings[text]
  if (translated === undefined) missing.add(text)
  return fill(translated ?? text, vars)
}

export function tServer(text) {
  if (LANG === 'it' || typeof text !== 'string' || !text) return text
  if (text in en.strings) return en.strings[text]
  for (const [pattern, replacement] of en.patterns) {
    if (pattern.test(text)) return text.replace(pattern, replacement)
  }
  if (text.includes('\n')) return text.split('\n').map(tServer).join('\n')
  missing.add(`[server] ${text}`)
  return text
}

/** Singolare o plurale: tn(3, '1 modifica', '{n} modifiche') -> "3 modifiche" (tradotto). */
export function tn(n, one, many, vars) {
  return t(n === 1 ? one : many, { n, ...vars })
}

/** Stessa parola italiana, traduzioni diverse: tc('ruolo', 'Modifica') -> "Editor" (chiave "ruolo|Modifica" in en.js). */
export function tc(context, text, vars) {
  if (LANG === 'it') return fill(text, vars)
  const translated = en.strings[`${context}|${text}`]
  return translated === undefined ? t(text, vars) : fill(translated, vars)
}

/**
 * Valori ed etichette che sono dati (nomi di device, posizioni, valori nello storico e nelle differenze): solo i
 * modelli, mai le frasi esatte, così una posizione chiamata "Primo piano" resta com'è.
 */
export function tData(text) {
  if (LANG === 'it' || typeof text !== 'string' || !text) return text
  for (const [pattern, replacement] of en.patterns) {
    if (pattern.test(text)) return text.replace(pattern, replacement)
  }
  return text
}
