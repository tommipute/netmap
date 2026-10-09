// Numero dell'ultima release (semver): si cambia solo facendo una release, e il workflow controlla che coincida con
// il tag. Nelle immagini arriva dal build (VITE_APP_VERSION); le installazioni con git mostrano quello calcolato
// dall'updater (es. 1.0.0+3, tre modifiche dopo la 1.0.0), che arriva da /api/version.
export const VERSION = import.meta.env.VITE_APP_VERSION || '1.0.0'
