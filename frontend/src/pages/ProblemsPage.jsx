import { Link, useSearchParams } from 'react-router-dom'
import { qs } from '../api'
import { ErrorBox, Loading } from '../components/Bits'
import { PageIcon } from '../components/Icon'
import { ProblemTable } from '../components/Problems'
import { useApi } from '../hooks'
import { PROBLEM_KINDS, SEVERITIES } from '../options'
import { t, tn } from '../i18n'

export default function ProblemsPage() {
  const [params, setParams] = useSearchParams()
  const severity = params.get('severity') || ''
  const kind = params.get('kind') || ''
  const siteId = params.get('site_id') || ''
  const { data, error, loading } = useApi(`/problems${qs({ severity, kind, site_id: siteId })}`)
  const sites = useApi('/sites?limit=500').data

  const set = (name, value) => setParams((prev) => {
    const next = new URLSearchParams(prev)
    if (value) next.set(name, value)
    else next.delete(name)
    return next
  }, { replace: true })

  return (
    <div className="page">
      <header className="page-head">
        <div>
          <h1 className="page-title"><PageIcon name="alert" />{t('Problemi rilevati')}</h1>
          <p className="page-intro">
            {t('Cose che non vanno nella rete, trovate con quello che NetMap legge dagli switch (monitor ogni 5 minuti, tabelle MAC e ARP dalle scansioni). Si aggiornano da soli: quando il problema sparisce, sparisce anche da qui.')}
          </p>
        </div>
      </header>

      {data && (
        <div className="problem-counts" role="group" aria-label={t('Priorità')}>
          {SEVERITIES.map((level) => (
            <button
              key={level.value}
              type="button"
              className={`problem-count problem-count--${level.value}${severity === level.value ? ' problem-count--on' : ''}`}
              aria-pressed={severity === level.value}
              onClick={() => set('severity', severity === level.value ? '' : level.value)}
            >
              <strong>{data.counts[level.value]}</strong>
              <span>{level.label}</span>
            </button>
          ))}
        </div>
      )}

      <div className="toolbar">
        <select className="input" aria-label={t('Tipo di problema')} value={kind} onChange={(e) => set('kind', e.target.value)}>
          <option value="">{t('Tutti i tipi')}</option>
          {PROBLEM_KINDS.map((k) => <option key={k.value} value={k.value}>{k.label}</option>)}
        </select>
        {sites && sites.total > 1 && (
          <select className="input" aria-label={t('Sede')} value={siteId} onChange={(e) => set('site_id', e.target.value)}>
            <option value="">{t('Tutte le sedi')}</option>
            {sites.items.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
          </select>
        )}
        {data && <span className="toolbar__count">{tn(data.total, '1 problema', '{n} problemi')}</span>}
      </div>

      <ErrorBox error={error} />
      {!data && loading && <Loading />}
      {data && data.total === 0 && (
        <div className="empty">
          <p>
            {severity || kind || siteId
              ? t('Nessun problema con questi filtri.')
              : t('Nessun problema rilevato. Servono il monitor acceso e un profilo SNMP sui device; le tabelle MAC arrivano dalle')}{' '}
            {!(severity || kind || siteId) && <Link to="/discovery-jobs">{t('Scansioni')}</Link>}
          </p>
        </div>
      )}
      {data && data.total > 0 && <ProblemTable items={data.items} />}
    </div>
  )
}
