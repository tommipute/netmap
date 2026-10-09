import { useCallback, useEffect, useId, useMemo, useRef, useState } from 'react'
import { api } from '../api'
import { ErrorBox, Loading } from '../components/Bits'
import { Icon, IconButton } from '../components/Icon'
import { invalidate, useApi } from '../hooks'
import { RUN_STATUS, formatDateTime, formatDuration } from '../options'
import { t, tServer, tn } from '../i18n'

const RUN_TONE = { queued: 'muted', running: 'info', done: 'ok', failed: 'danger' }

// Righe della tabella dei risultati, nell'ordine dell'import (chiavi di KINDS in services/netbox.py)
const KINDS = [
  ['site', t('Sedi')], ['location', t('Posizioni')], ['rack', t('Rack')], ['manufacturer', t('Produttori')],
  ['device_role', t('Ruoli')], ['device_type', t('Modelli')], ['vrf', t('VRF')], ['vlan', t('VLAN')],
  ['prefix', t('Subnet')], ['device', t('Device')], ['stack_member', t('Membri degli stack')],
  ['interface', t('Porte')], ['cable', t('Cavi')], ['ip', t('Indirizzi IP')],
]
const kindLabel = (kind) => KINDS.find(([k]) => k === kind)?.[1] ?? kind

const COUNTS = [
  ['devices', '1 device', '{n} device'], ['interfaces', '1 porta', '{n} porte'], ['cables', '1 cavo', '{n} cavi'],
  ['vlans', '1 VLAN', '{n} VLAN'], ['prefixes', '1 subnet', '{n} subnet'], ['ip_addresses', '1 IP', '{n} IP'],
  ['sites', '1 sede', '{n} sedi'],
]

const active = (run) => run && (run.status === 'queued' || run.status === 'running')
const total = (counts, key) => Object.values(counts || {}).reduce((sum, c) => sum + (c[key] || 0), 0)

function RunStatus({ run }) {
  const label = RUN_STATUS.find((o) => o.value === run.status)?.label ?? run.status
  return (
    <span className={`badge badge--${RUN_TONE[run.status] || 'muted'}`}>
      {active(run) && <span className="update-spinner" aria-hidden="true" />}
      {label}
    </span>
  )
}

function TextField({ label, value, onChange, hint, placeholder, type = 'text', required }) {
  const id = useId()
  return (
    <div className="field">
      <label className="field__label" htmlFor={id}>
        {label}
        {required && <span className="field__req" aria-hidden="true"> *</span>}
      </label>
      <input id={id} className="input" type={type} value={value} placeholder={placeholder} autoComplete="off"
        spellCheck={false} onChange={(e) => onChange(e.target.value)} />
      {hint && <span className="hint">{hint}</span>}
    </div>
  )
}

/** Sedi di NetBox da importare: tutte, oppure quelle spuntate (con ricerca se sono tante). */
function SitePicker({ sites, chosen, setChosen }) {
  const [query, setQuery] = useState('')
  const all = chosen === null
  const shown = useMemo(() => {
    const q = query.trim().toLowerCase()
    return q ? sites.filter((s) => s.name.toLowerCase().includes(q)) : sites
  }, [sites, query])
  const toggle = (id) => setChosen((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]))

  return (
    <div className="netbox-sites">
      <div className="segmented" role="group" aria-label={t('Sedi da importare')}>
        <button type="button" className={`segmented__item${all ? ' segmented__item--on' : ''}`} aria-pressed={all}
          onClick={() => setChosen(null)}>{t('Tutte le sedi')}</button>
        <button type="button" className={`segmented__item${all ? '' : ' segmented__item--on'}`} aria-pressed={!all}
          onClick={() => setChosen(chosen ?? [])}>{t('Solo le sedi scelte')}</button>
      </div>
      {!all && (
        <>
          {sites.length > 8 && (
            <input className="input netbox-sites__search" type="search" value={query} placeholder={t('Cerca una sede')}
              aria-label={t('Cerca una sede')} onChange={(e) => setQuery(e.target.value)} />
          )}
          <ul className="netbox-sites__list">
            {shown.map((s) => (
              <li key={s.id}>
                <label className="check">
                  <input type="checkbox" checked={chosen.includes(s.id)} onChange={() => toggle(s.id)} />
                  <span>{s.name}</span>
                  <span className="muted">{tn(s.devices, '1 device', '{n} device')}</span>
                </label>
              </li>
            ))}
            {shown.length === 0 && <li className="muted">{t('Nessuna sede con questo nome.')}</li>}
          </ul>
          <span className="hint">{tn(chosen.length, '1 sede scelta', '{n} sedi scelte')}</span>
        </>
      )}
    </div>
  )
}

/** Stato, log, numeri e problemi di un import (si aggiorna da solo mentre il worker lavora). */
function RunDetail({ run }) {
  const counts = run.counts || {}
  const kinds = KINDS.filter(([k]) => counts[k] && Object.values(counts[k]).some(Boolean))
  return (
    <div className="netbox-run">
      <div className="update-live">
        <RunStatus run={run} />
        <span>
          {run.dry_run ? t('Simulazione') : t('Import')}{' '}
          {run.site_names.length ? tn(run.site_names.length, 'della sede {names}', 'delle sedi {names}', { names: run.site_names.join(', ') })
            : run.site_ids.length ? tn(run.site_ids.length, 'di 1 sede', 'di {n} sedi') : t('di tutte le sedi')}
        </span>
        <span className="muted">
          {[run.netbox_version && `NetBox ${run.netbox_version}`, run.requested_by,
            formatDateTime(run.started_at || run.requested_at),
            run.finished_at && formatDuration(run.started_at, run.finished_at)].filter(Boolean).join(' · ')}
        </span>
      </div>
      {run.status === 'done' && run.dry_run && (
        <p className="notice">{t('Era una simulazione: niente è stato salvato. Se i numeri ti convincono, premi "Importa".')}</p>
      )}
      <pre className="log update-log">{tServer(run.log) || (run.status === 'queued' ? t('In attesa del worker…') : t('Nessun messaggio.'))}</pre>
      {kinds.length > 0 && (
        <div className="table-wrap netbox-counts">
          <table className="table table--dense">
            <thead>
              <tr>
                <th>{t('Oggetti')}</th>
                <th className="num">{run.dry_run ? t('Da creare') : t('Creati')}</th>
                <th className="num">{t('Già presenti')}</th>
                <th className="num">{t('Non importati')}</th>
                <th className="num">{t('Saltati')}</th>
              </tr>
            </thead>
            <tbody>
              {kinds.map(([kind, label]) => (
                <tr key={kind}>
                  <td>{label}</td>
                  <td className="num">{counts[kind].created || ''}</td>
                  <td className="num">{counts[kind].existing || ''}</td>
                  <td className="num">{counts[kind].failed ? <strong className="backup-msg--error">{counts[kind].failed}</strong> : ''}</td>
                  <td className="num">{counts[kind].skipped || ''}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="hint">{t('Già presenti: c\'erano già in NetMap (stesso nome) e restano come sono. Saltati: porte dei device che c\'erano già, cavi verso circuiti, prese elettriche o altre sedi.')}</p>
        </div>
      )}
      {run.problems?.length > 0 && (
        <section className="netbox-problems">
          <h3>{tn(run.problems.length, '1 problema', '{n} problemi')}</h3>
          <div className="table-wrap">
            <table className="table table--dense">
              <thead><tr><th>{t('Oggetti')}</th><th>{t('Nome')}</th><th>{t('Motivo')}</th></tr></thead>
              <tbody>
                {run.problems.map((p, index) => (
                  <tr key={index}>
                    <td>{kindLabel(p.kind)}</td>
                    <td className="mono">{p.name}</td>
                    <td>{tServer(p.message)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </div>
  )
}

export default function NetBoxImportPage() {
  const { data: runs, error: runsError, reload: reloadRuns } = useApi('/netbox/imports')
  const [conn, setConn] = useState({ url: '', token: '', verify_tls: true })
  const [probe, setProbe] = useState(null)
  const [chosen, setChosen] = useState(null) // null = tutte le sedi
  const [busy, setBusy] = useState(null) // 'test' | 'dry' | 'real'
  const [error, setError] = useState(null)
  const [openId, setOpenId] = useState(null)
  const [run, setRun] = useState(null)
  const started = useRef(false)

  const setField = (name, value) => {
    setConn((prev) => ({ ...prev, [name]: value }))
    setProbe(null) // un'altra connessione: sedi e numeri vanno riletti
    setChosen(null)
  }

  // All'apertura: se c'è un import in corso lo mostro, e riprendo l'indirizzo dell'ultimo
  useEffect(() => {
    if (!runs || started.current) return
    started.current = true
    if (!runs.length) return
    if (active(runs[0])) setOpenId(runs[0].id)
    setConn((prev) => (prev.url ? prev : { ...prev, url: runs[0].url, verify_tls: runs[0].verify_tls }))
  }, [runs])

  const loadRun = useCallback(async (id) => {
    try {
      setRun(await api.get(`/netbox/imports/${id}`))
    } catch (err) {
      setError(err)
    }
  }, [])

  useEffect(() => {
    if (openId === null) return
    setRun((prev) => (prev?.id === openId ? prev : null))
    loadRun(openId)
  }, [openId, loadRun])

  // Mentre il worker lavora, log e numeri ogni 2 secondi; alla fine aggiorno elenco e menu
  const running = run?.id === openId && active(run)
  useEffect(() => {
    if (!running) return undefined
    const timer = setInterval(() => loadRun(openId), 2000)
    return () => {
      clearInterval(timer)
      reloadRuns()
      invalidate()
    }
  }, [running, openId, loadRun, reloadRuns])

  const test = async (e) => {
    e.preventDefault()
    setBusy('test')
    setError(null)
    setProbe(null)
    try {
      setProbe(await api.post('/netbox/test', conn))
    } catch (err) {
      setError(err)
    } finally {
      setBusy(null)
    }
  }

  const start = async (dryRun) => {
    if (!dryRun && !window.confirm(t('Importare da NetBox? Gli oggetti che mancano vengono creati in NetMap; quelli che ci sono già restano come sono.'))) return
    setBusy(dryRun ? 'dry' : 'real')
    setError(null)
    try {
      const created = await api.post('/netbox/imports', { ...conn, site_ids: chosen ?? [], dry_run: dryRun })
      setRun(created)
      setOpenId(created.id)
      reloadRuns()
    } catch (err) {
      setError(err)
    } finally {
      setBusy(null)
    }
  }

  if (runsError) return <div className="page"><ErrorBox error={runsError} /></div>
  if (!runs) return <Loading />

  const someoneRunning = active(run) || runs.some(active)
  const noSites = chosen !== null && chosen.length === 0

  return (
    <div className="page netbox-page">
      <header className="page-head">
        <div>
          <h1>{t('Import da NetBox')}</h1>
          <p className="page-intro">
            {t('Copia in NetMap sedi, posizioni, rack, device con porte e stack, cavi, VLAN, subnet e indirizzi IP da NetBox (versione 3.3 o successiva). Crea solo quello che manca: gli oggetti che ci sono già in NetMap, con lo stesso nome, restano come sono. Prova prima con la simulazione.')}
          </p>
        </div>
      </header>

      <form className="form" onSubmit={test}>
        <section className="section">
          <header className="section__head"><h2>{t('Connessione')}</h2></header>
          <div className="form__grid">
            <TextField label={t('Indirizzo di NetBox')} value={conn.url} onChange={(v) => setField('url', v)} required
              placeholder="https://netbox.azienda.local" hint={t('Quello che apri nel browser, senza /api.')} />
            <TextField label={t('Token API')} type="password" value={conn.token} onChange={(v) => setField('token', v)} required
              hint={t('Basta un token in sola lettura (in NetBox: il tuo profilo, Token API). Non resta salvato: il worker lo cancella a fine import.')} />
            <div className="field field--wide">
              <label className="check">
                <input type="checkbox" checked={conn.verify_tls} onChange={(e) => setField('verify_tls', e.target.checked)} />
                {t('Verifica il certificato HTTPS di NetBox')}
              </label>
              {!conn.verify_tls && <span className="hint">{t('Spegnila solo se NetBox ha un certificato autofirmato: il token passa comunque cifrato.')}</span>}
            </div>
          </div>
          <div className="update-actions netbox-actions">
            <button type="submit" className="btn" disabled={busy !== null || !conn.url.trim() || !conn.token.trim()}>
              <Icon name="key" /> {busy === 'test' ? t('Prova in corso…') : t('Prova la connessione')}
            </button>
          </div>
        </section>
      </form>

      <ErrorBox error={error} />

      {probe && (
        <section className="section">
          <header className="section__head"><h2>{t('Cosa importare')}</h2></header>
          <p className="notice">
            {t('Connesso a NetBox {version}: {counts}.', {
              version: probe.version,
              counts: COUNTS.map(([key, one, many]) => tn(probe.counts[key] ?? 0, one, many)).join(', '),
            })}
          </p>
          <SitePicker sites={probe.sites} chosen={chosen} setChosen={setChosen} />
          <p className="hint netbox-note">
            {t('Uno stack di NetBox (virtual chassis) diventa un device solo con i suoi membri. I cavi che passano da un patch panel diventano un cavo da porta a porta con il patch panel nelle note. Le porte di un device che c\'era già in NetMap restano come sono.')}
          </p>
          <div className="update-actions">
            <button type="button" className="btn" disabled={busy !== null || someoneRunning || noSites} onClick={() => start(true)}>
              <Icon name="play" /> {busy === 'dry' ? t('Avvio…') : t("Simula l'import")}
            </button>
            <button type="button" className="btn btn--primary" disabled={busy !== null || someoneRunning || noSites} onClick={() => start(false)}>
              <Icon name="upload" /> {busy === 'real' ? t('Avvio…') : t('Importa')}
            </button>
            {someoneRunning && <span className="hint">{t("C'è già un import in corso: aspetta che finisca.")}</span>}
          </div>
        </section>
      )}

      {run && run.id === openId && (
        <section className="section">
          <header className="section__head"><h2>{run.dry_run ? t('Simulazione') : t('Import')}</h2></header>
          <RunDetail run={run} />
        </section>
      )}

      <section className="section">
        <header className="section__head">
          <h2>{t('Import precedenti')}{runs.length > 0 && <span className="section__count">{t('ultimi {n}', { n: runs.length })}</span>}</h2>
        </header>
        {runs.length === 0 ? (
          <div className="empty"><p>{t('Nessun import da NetBox finora.')}</p></div>
        ) : (
          <div className="table-wrap">
            <table className="table table--dense">
              <thead>
                <tr>
                  <th>{t('Avviato')}</th>
                  <th>{t('Tipo')}</th>
                  <th>{t('Stato')}</th>
                  <th>{t('Sedi')}</th>
                  <th className="num">{t('Creati')}</th>
                  <th className="num">{t('Già presenti')}</th>
                  <th className="num">{t('Non importati')}</th>
                  <th>{t('Utente')}</th>
                  <th className="table__actions"><span className="sr-only">{t('Dettagli')}</span></th>
                </tr>
              </thead>
              <tbody>
                {runs.map((r) => (
                  <tr key={r.id} className={r.id === openId ? 'is-selected' : undefined}>
                    <td>{formatDateTime(r.started_at || r.requested_at)}</td>
                    <td>{r.dry_run ? t('Simulazione') : t('Import')}</td>
                    <td><RunStatus run={r} /></td>
                    <td>{r.site_names.join(', ') || (r.site_ids.length ? tn(r.site_ids.length, '1 sede', '{n} sedi') : t('Tutte'))}</td>
                    <td className="num">{total(r.counts, 'created')}</td>
                    <td className="num">{total(r.counts, 'existing')}</td>
                    <td className="num">{total(r.counts, 'failed') || ''}</td>
                    <td>{r.requested_by || '—'}</td>
                    <td className="table__actions">
                      <IconButton icon="log" small label={r.id === openId ? t('Nascondi dettagli') : t('Mostra dettagli')}
                        className={r.id === openId ? 'btn--ghost is-on' : 'btn--ghost'} aria-expanded={r.id === openId}
                        onClick={() => setOpenId(r.id === openId ? null : r.id)} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  )
}
