/**
 * Preferenze dell'interfaccia nel browser (chiavi localStorage "netmap.*": tema, lingua, menu, colonne delle
 * tabelle, caselle della mappa…) e loro copia sul server per l'utente collegato, così lo seguono su ogni computer.
 * Chi scrive una preferenza usa store(): la copia sul server parte subito.
 */
const PREFIX = 'netmap.'
let syncing = false

export function readLocal(key) {
  try {
    return localStorage.getItem(key)
  } catch {
    return null
  }
}

/** Salva (null = toglie) e la manda al server. */
export function store(key, value) {
  try {
    if (value === null || value === undefined) localStorage.removeItem(key)
    else localStorage.setItem(key, value)
  } catch {
    // senza storage la scelta vale finché la pagina resta aperta
  }
  push()
}

function collect() {
  const all = {}
  try {
    for (let i = 0; i < localStorage.length; i += 1) {
      const key = localStorage.key(i)
      if (key.startsWith(PREFIX)) all[key] = localStorage.getItem(key)
    }
  } catch {
    // niente storage, niente preferenze
  }
  return all
}

// keepalive: la richiesta arriva anche se la pagina si ricarica subito dopo (cambio di lingua)
function push() {
  if (!syncing) return
  fetch('/api/auth/me/preferences', {
    method: 'PUT', keepalive: true, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(collect()),
  }).catch(() => {})
}

/** Tema e densità sull'elemento <html> (anche index.html lo fa prima del primo disegno). */
export function applyDocument() {
  const root = document.documentElement
  const theme = readLocal('netmap.theme')
  if (theme === 'light' || theme === 'dark') root.dataset.theme = theme
  else delete root.dataset.theme
  if (readLocal('netmap.density') === 'compact') root.dataset.density = 'compact'
  else delete root.dataset.density
}

const langOf = (value) => (value === 'en' ? 'en' : 'it')

/**
 * Dopo l'accesso, prima di disegnare l'app: le preferenze salvate per l'utente prendono il posto di quelle del
 * browser. La prima volta (sul server non c'è niente) il contrario: si salvano quelle del browser.
 * true = la lingua è diversa e la pagina si ricarica.
 */
export function startSync(saved) {
  syncing = true
  if (!saved || Object.keys(saved).length === 0) {
    push()
    return false
  }
  const lang = langOf(readLocal('netmap.lang'))
  try {
    Object.keys(collect()).filter((key) => !(key in saved)).forEach((key) => localStorage.removeItem(key))
    Object.entries(saved).forEach(([key, value]) => localStorage.setItem(key, value))
  } catch {
    return false
  }
  applyDocument()
  if (langOf(readLocal('netmap.lang')) !== lang) {
    window.location.reload()
    return true
  }
  return false
}

/** Dopo l'uscita le scelte restano nel browser, ma non vanno più al server. */
export function stopSync() {
  syncing = false
}
