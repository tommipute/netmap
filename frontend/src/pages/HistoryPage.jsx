import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { qs } from '../api'
import { ErrorBox, Loading } from '../components/Bits'
import HistoryList, { OBJECT_TYPES, SOURCES } from '../components/HistoryList'
import { IconButton } from '../components/Icon'
import RefLabel from '../components/RefLabel'
import { useApi, useDebounced } from '../hooks'
import { formatDateTime } from '../options'
import { t, tn } from '../i18n'

const LIMIT = 50

/** Storico delle modifiche: chi ha cambiato cosa e quando. Filtri nell'indirizzo (device_id, object_type, source, q). */
export default function HistoryPage() {
  const [params, setParams] = useSearchParams()
  const [search, setSearch] = useState(params.get('q') || '')
  const [offset, setOffset] = useState(0)
  const q = useDebounced(search.trim())
  const deviceId = params.get('device_id')
  const objectType = params.get('object_type') || ''
  const source = params.get('source') || ''
  const since = params.get('since') || '' // da "Cosa è cambiato": solo le modifiche del periodo

  const setFilter = (name, value) =>
    setParams((prev) => {
      const next = new URLSearchParams(prev)
      if (value) next.set(name, value)
      else next.delete(name)
      return next
    }, { replace: true })

  useEffect(() => setFilter('q', q), [q]) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => setOffset(0), [q, deviceId, objectType, source, since])

  const { data, error, loading } = useApi(
    `/audit-log${qs({ q, device_id: deviceId, object_type: objectType, source, since, limit: LIMIT, offset })}`,
  )

  return (
    <div className="page">
      <header className="page-head">
        <div>
          <h1>{t('Storico modifiche')}</h1>
          <p className="page-intro">
            {t("Chi ha cambiato cosa e quando: a mano, con la scansione SNMP o con l'import. Lo stato live e i dati che la scansione aggiorna da sola (ultima volta visto, porte su/giù) non compaiono.")}
          </p>
        </div>
      </header>

      <div className="toolbar">
        <input type="search" className="input toolbar__search" placeholder={t('Cerca per nome o utente')} value={search}
          aria-label={t('Cerca nello storico')} onChange={(e) => setSearch(e.target.value)} />
        <select className="input" value={objectType} aria-label={t('Tipo di oggetto')} onChange={(e) => setFilter('object_type', e.target.value)}>
          <option value="">{t('Tutti gli oggetti')}</option>
          {OBJECT_TYPES.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
        </select>
        <select className="input" value={source} aria-label={t('Origine')} onChange={(e) => setFilter('source', e.target.value)}>
          <option value="">{t('Tutte le origini')}</option>
          {SOURCES.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
        </select>
        {deviceId && (
          <span className="filter-chip">
            Device <RefLabel resource="devices" id={Number(deviceId)} />
            <IconButton icon="close" label={t('Togli il filtro del device')} small className="btn--ghost" onClick={() => setFilter('device_id', '')} />
          </span>
        )}
        {since && (
          <span className="filter-chip">
            Dal {formatDateTime(since)}
            <IconButton icon="close" label={t('Togli il filtro della data')} small className="btn--ghost" onClick={() => setFilter('since', '')} />
          </span>
        )}
        {data && <span className="toolbar__count">{tn(data.total, '1 modifica', '{n} modifiche')}</span>}
      </div>

      <ErrorBox error={error} />
      {!data && loading && <Loading />}
      {data && data.items.length === 0 && <div className="empty"><p>{t('Nessuna modifica con questi filtri.')}</p></div>}
      {data && data.items.length > 0 && <HistoryList entries={data.items} />}

      {data && data.total > LIMIT && (
        <div className="pager">
          <IconButton icon="prev" label={t('Pagina precedente')} small className="btn--ghost" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - LIMIT))} />
          <span>{offset + 1}–{Math.min(offset + LIMIT, data.total)} di {data.total}</span>
          <IconButton icon="next" label={t('Pagina successiva')} small className="btn--ghost" disabled={offset + LIMIT >= data.total} onClick={() => setOffset(offset + LIMIT)} />
        </div>
      )}
    </div>
  )
}
