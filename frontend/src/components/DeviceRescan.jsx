import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'
import { t } from '../i18n'

const ACTIVE = ['queued', 'running']

/**
 * "Rileggi ora": rilettura via SNMP del solo device, con il job dell'ultima lettura. Segue l'esecuzione finché
 * finisce (anche se era già partita prima di aprire la pagina: `report.host_run`) e poi chiama `onDone`.
 */
export function useRescan(deviceId, report, onDone) {
  const [run, setRun] = useState(null)
  const done = useRef(onDone)
  done.current = onDone
  const pending = report?.host_run

  useEffect(() => {
    if (pending) setRun(pending)
  }, [pending?.id]) // eslint-disable-line react-hooks/exhaustive-deps

  const active = Boolean(run && ACTIVE.includes(run.status))
  useEffect(() => {
    if (!active) return undefined
    const timer = setInterval(async () => {
      try {
        const next = await api.get(`/discovery-runs/${run.id}`)
        setRun(next)
        if (!ACTIVE.includes(next.status)) done.current()
      } catch { /* riprova al giro dopo */ }
    }, 2000)
    return () => clearInterval(timer)
  }, [active, run?.id]) // eslint-disable-line react-hooks/exhaustive-deps

  const start = async () => {
    try {
      setRun(await api.post(`/devices/${deviceId}/rescan`))
    } catch (err) {
      window.alert(err.message)
    }
  }
  return { run, active, start, dismiss: () => setRun(null) }
}

/** Avviso sotto il titolo: rilettura in corso o com'è andata. */
export function RescanNotice({ run, onClose }) {
  if (!run) return null
  const log = <Link to={`/discovery-jobs/${run.job_id}`}>{t('Vedi il log')}</Link>
  let tone = ''
  let text
  if (ACTIVE.includes(run.status)) {
    text = t('Rilettura via SNMP in corso…')
  } else if (run.status !== 'done') {
    tone = 'notice--warn'
    text = <>{t('Rilettura non riuscita.')} {log}</>
  } else if (run.hosts_responded === 0) {
    tone = 'notice--warn'
    text = <>{t('L\'apparato non ha risposto: controlla che sia acceso e raggiungibile e il profilo SNMP.')} {log}</>
  } else {
    text = t('Rilettura finita: {applied} modifiche applicate, {proposed} da approvare.', { applied: run.changes_applied, proposed: run.changes_proposed })
  }
  return (
    <p className={`notice no-print rescan-notice ${tone}`}>
      <span>{text}</span>
      {!ACTIVE.includes(run.status) && (
        <button type="button" className="btn btn--ghost btn--sm" onClick={onClose} aria-label={t('Chiudi')}>×</button>
      )}
    </p>
  )
}
