import { useEffect, useState } from 'react'
import { api } from '../api'
import { useApi } from '../hooks'
import { t, tServer } from '../i18n'

/** Parti in comune delle pagine Aggiornamenti e Backup: entrambe leggono lo stato dello script sull'host. */

export const BUSY = {
  checking: t('Controllo in corso'),
  updating: t('Aggiornamento in corso'),
  rolling_back: t('Rollback in corso'),
  backup: t('Backup in corso'),
  restoring: t('Ripristino in corso'),
}

// I messaggi dello script sono frasi italiane: le traduco una per una
export const tMessage = (text) => (text || '').split(/(?<=\.)\s+/).map((part) => tServer(part)).join(' ')

/**
 * Stato dello script (/updates) aggiornato spesso mentre lavora o ha una richiesta in sospeso, altrimenti ogni
 * tanto. Durante un aggiornamento l'API si riavvia: resta l'ultimo stato ricevuto e offline diventa true.
 */
export function useUpdater() {
  const { data: fresh, error, reload } = useApi('/updates')
  const [lastData, setLastData] = useState(null)
  useEffect(() => { if (fresh) setLastData(fresh) }, [fresh])
  const data = fresh || lastData
  const offline = Boolean(error && lastData)
  const activity = data?.status?.activity
  const waiting = offline || Boolean(activity && activity !== 'idle') || Boolean(data?.request)
  const [sending, setSending] = useState(null)
  const [actionError, setActionError] = useState(null)

  useEffect(() => {
    const timer = setInterval(reload, waiting ? 3000 : 20000)
    return () => clearInterval(timer)
  }, [waiting, reload])

  /** Chiede un'azione allo script ("check", "update", "backup"); true se la richiesta è partita. */
  const send = async (action) => {
    setSending(action)
    setActionError(null)
    try {
      await api.post('/updates/request', { action })
      reload()
      return true
    } catch (err) {
      setActionError(err)
      return false
    } finally {
      setSending(null)
    }
  }

  return { data, error: data ? null : error, offline, waiting, reload, send, sending, actionError }
}

/** Avvisi quando lo script non c'è, non è mai partito o tace da troppo. */
export function ScriptWarning({ data }) {
  const steps = (
    <p className="hint">{t('Sul server, nella cartella di NetMap: sudo updater/install.sh, poi docker compose up -d. Istruzioni complete nel README, sezione «Aggiornamenti automatici».')}</p>
  )
  if (data.script === 'not_mounted') {
    return (
      <div className="notice notice--warn">
        <strong>{t("La cartella condivisa con l'updater non è montata.")}</strong>{' '}
        {t("L'app non può vedere né chiedere aggiornamenti: il container api deve montare updater-data in /updater-data (docker-compose.yml aggiornato).")}
        {steps}
      </div>
    )
  }
  if (data.script === 'never_ran') {
    return (
      <div className="notice notice--warn">
        <strong>{t("Lo script di aggiornamento non è mai partito.")}</strong>{' '}
        {t('La cartella è montata ma lo script non ha ancora scritto lo stato: probabilmente non è installato sul server.')}
        {steps}
      </div>
    )
  }
  if (data.script === 'silent' || data.script === 'stuck') {
    return (
      <div className="notice notice--warn">
        <strong>
          {data.script === 'stuck'
            ? t("Lo script sembra bloccato a metà di un'operazione.")
            : t('Lo script tace da {n} minuti (dovrebbe girare ogni minuto).', { n: data.silent_minutes ?? '?' })}
        </strong>{' '}
        {t('Sul server controlla il timer: systemctl status netmap-updater.timer e journalctl -u netmap-updater.')}
      </div>
    )
  }
  return null
}
