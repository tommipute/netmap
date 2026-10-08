// Versione mostrata in basso al centro di ogni pagina. Da aggiornare a ogni commit che va su GitHub:
// data di oggi + numero progressivo del giorno (es. 2026.10.08-2), così dal PC si vede quale ZIP è installato.
// Nelle immagini pubblicate (release vX.Y.Z) vale invece il numero della release, passato al build.
export const VERSION = import.meta.env.VITE_APP_VERSION || '2026.10.09-1'
