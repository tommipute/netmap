import { useCallback, useEffect, useId, useMemo, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { api } from '../api'
import { ErrorBox, Loading } from '../components/Bits'
import DeviceImportDialog from '../components/DeviceImportDialog'
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

// Cosa si sceglie in ogni sorgente (sedi di NetBox, gruppi di host di Zabbix…): parole per la scelta e i conteggi
const GROUPS = {
  sites: {
    title: t('Sedi da importare'), all: t('Tutte le sedi'), some: t('Solo le sedi scelte'), search: t('Cerca una sede'),
    none: t('Nessuna sede con questo nome.'), chosen: ['1 sede scelta', '{n} sedi scelte'], count: ['1 sede', '{n} sedi'],
  },
  hostgroups: {
    title: t('Gruppi di host da importare'), all: t('Tutti i gruppi'), some: t('Solo i gruppi scelti'),
    search: t('Cerca un gruppo'), none: t('Nessun gruppo con questo nome.'), chosen: ['1 gruppo scelto', '{n} gruppi scelti'],
    count: ['1 gruppo', '{n} gruppi'],
  },
  locations: {
    title: t('Posizioni da importare'), all: t('Tutte le posizioni'), some: t('Solo le posizioni scelte'),
    search: t('Cerca una posizione'), none: t('Nessuna posizione con questo nome.'),
    chosen: ['1 posizione scelta', '{n} posizioni scelte'], count: ['1 posizione', '{n} posizioni'],
  },
  probes: {
    title: t('Sonde da importare'), all: t('Tutte le sonde'), some: t('Solo le sonde scelte'), search: t('Cerca una sonda'),
    none: t('Nessuna sonda con questo nome.'), chosen: ['1 sonda scelta', '{n} sonde scelte'], count: ['1 sonda', '{n} sonde'],
  },
  lansites: {
    title: t('Siti da importare'), all: t('Tutti i siti'), some: t('Solo i siti scelti'), search: t('Cerca un sito'),
    none: t('Nessun sito con questo nome.'), chosen: ['1 sito scelto', '{n} siti scelti'], count: ['1 sito', '{n} siti'],
  },
}

const SAVED = t('Non resta salvato: il worker lo cancella a fine import.')

// Sorgenti: campi della connessione e testi (le chiavi sono quelle di services/connectors.py)
export const IMPORT_SOURCES = [
  {
    key: 'csv', label: t('CSV o Excel'),
    intro: t('Device da un file CSV o Excel (.xlsx), con sede, posizione, rack, modello, ruolo, IP di management e campi personalizzati. Si possono anche aggiornare i device che ci sono già. Il modello del file si scarica dalla finestra di import.'),
  },
  {
    key: 'netbox', label: 'NetBox', groups: GROUPS.sites,
    intro: t('Copia in NetMap sedi, posizioni, rack, device con porte e stack, cavi, VLAN, subnet e indirizzi IP da NetBox (versione 3.3 o successiva). Crea solo quello che manca: gli oggetti che ci sono già in NetMap, con lo stesso nome, restano come sono. Prova prima con la simulazione.'),
    url: { label: t('Indirizzo di NetBox'), placeholder: 'https://netbox.azienda.local', hint: t('Quello che apri nel browser, senza /api.') },
    token: { label: t('Token API'), hint: t('Basta un token in sola lettura (in NetBox: il tuo profilo, Token API).') },
    note: t('Uno stack di NetBox (virtual chassis) diventa un device solo con i suoi membri. I cavi che passano da un patch panel diventano un cavo da porta a porta con il patch panel nelle note. Le porte di un device che c\'era già in NetMap restano come sono.'),
  },
  {
    key: 'zabbix', label: 'Zabbix', groups: GROUPS.hostgroups, defaultSite: true,
    intro: t('Copia in NetMap gli host di Zabbix (5.0 o successivo) con l\'IP di management e i dati dell\'inventario: tipo (diventa il ruolo), produttore, modello, seriale, asset tag e posizione. Zabbix non ha sedi: gli host vanno nella sede scelta qui sotto.'),
    url: { label: t('Indirizzo di Zabbix'), placeholder: 'https://zabbix.azienda.local/zabbix', hint: t('Quello dell\'interfaccia web (la cartella con api_jsonrpc.php).') },
    username: { hint: t('Vuoto se usi un token API (Zabbix 5.4 o successivo).') },
    token: { label: t('Token API o password'), hint: t('Il token si crea in Zabbix in Utenti, Token API. Basta un utente che legge gli host.') },
  },
  {
    key: 'librenms', label: 'LibreNMS', groups: GROUPS.locations, defaultSite: true,
    intro: t('Copia in NetMap i device di LibreNMS con porte, indirizzi IP e vicini LLDP/CDP (diventano cavi). Le posizioni di LibreNMS diventano sedi; i device senza posizione vanno nella sede scelta qui sotto.'),
    url: { label: t('Indirizzo di LibreNMS'), placeholder: 'https://librenms.azienda.local', hint: t('Quello che apri nel browser, senza /api/v0.') },
    token: { label: t('Token API'), hint: t('In LibreNMS: menu dell\'utente, API Settings, crea un token.') },
  },
  {
    key: 'observium', label: 'Observium', groups: GROUPS.locations, defaultSite: true,
    intro: t('Copia in NetMap i device di Observium con le porte (serve un\'edizione con l\'API: Professional o Enterprise). Le posizioni diventano sedi; i device senza posizione vanno nella sede scelta qui sotto.'),
    url: { label: t('Indirizzo di Observium'), placeholder: 'https://observium.azienda.local', hint: t('Quello che apri nel browser.') },
    username: { required: true },
    token: { label: t('Password') },
  },
  {
    key: 'prtg', label: 'PRTG', groups: GROUPS.probes, defaultSite: true,
    intro: t('Copia in NetMap i device di PRTG: la sonda diventa la sede, il gruppo la posizione e l\'indirizzo del device, se è un IP, quello di management. PRTG non conosce porte e cavi.'),
    url: { label: t('Indirizzo di PRTG'), placeholder: 'https://prtg.azienda.local', hint: t('Quello che apri nel browser.') },
    username: { hint: t('Vuoto se usi una chiave API (PRTG 22.4 o successivo).') },
    token: { label: t('Chiave API, password o passhash'), hint: t('La chiave API si crea in PRTG nelle impostazioni dell\'account, Chiavi API, in sola lettura.') },
  },
  {
    key: 'glpi', label: 'GLPI', groups: GROUPS.sites, defaultSite: true,
    intro: t('Copia in NetMap gli apparati di rete di GLPI (9.5 o successivo) con porte, indirizzi IP e collegamenti tra le porte. Il primo livello della posizione diventa la sede, il resto la posizione; gli apparati senza posizione vanno nella sede scelta qui sotto.'),
    url: { label: t('Indirizzo di GLPI'), placeholder: 'https://glpi.azienda.local', hint: t('Quello che apri nel browser. L\'API REST va attivata in GLPI: Configurazione, Generale, API.') },
    username: { hint: t('Vuoto se usi il token dell\'utente.') },
    token: { label: t('Token dell\'utente o password'), hint: t('Il token si trova nelle impostazioni dell\'utente, Chiavi di accesso remoto, Token API.') },
    appToken: { hint: t('Solo se il client API di GLPI lo chiede.') },
  },
  {
    key: 'lansweeper', label: 'Lansweeper', groups: GROUPS.lansites,
    intro: t('Copia in NetMap gli apparati di rete di Lansweeper (cloud): switch, router, firewall, access point, stampanti, UPS, NAS. Computer e telefoni non si importano. Il sito di Lansweeper diventa la sede.'),
    url: { label: t('Indirizzo dell\'API'), placeholder: 'https://api.lansweeper.com/api/v2/graphql', hint: t('Vuoto per l\'API cloud di Lansweeper.'), optional: true },
    token: { label: t('Token personale'), hint: t('In Lansweeper: impostazioni, Developer tools, Personal access token (basta la lettura).') },
  },
]
const sourceOf = (key) => IMPORT_SOURCES.find((s) => s.key === key)
const sourceLabel = (key) => sourceOf(key)?.label ?? key
/** Cosa ha importato: i nomi delle sedi o dei gruppi scelti, altrimenti "Tutte le sedi" (o i gruppi). */
function scopeOf(run) {
  const words = sourceOf(run.source)?.groups ?? GROUPS.sites
  if (run.site_names.length) return run.site_names.join(', ')
  return run.site_ids.length ? tn(run.site_ids.length, ...words.chosen) : words.all
}

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

/** Sedi o gruppi da importare: tutti, oppure quelli spuntati (con ricerca se sono tanti). */
function GroupPicker({ groups: sites, words, chosen, setChosen }) {
  const [query, setQuery] = useState('')
  const all = chosen === null
  const shown = useMemo(() => {
    const q = query.trim().toLowerCase()
    return q ? sites.filter((s) => s.name.toLowerCase().includes(q)) : sites
  }, [sites, query])
  const toggle = (id) => setChosen((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]))

  return (
    <div className="netbox-sites">
      <div className="segmented" role="group" aria-label={words.title}>
        <button type="button" className={`segmented__item${all ? ' segmented__item--on' : ''}`} aria-pressed={all}
          onClick={() => setChosen(null)}>{words.all}</button>
        <button type="button" className={`segmented__item${all ? '' : ' segmented__item--on'}`} aria-pressed={!all}
          onClick={() => setChosen(chosen ?? [])}>{words.some}</button>
      </div>
      {!all && (
        <>
          {sites.length > 8 && (
            <input className="input netbox-sites__search" type="search" value={query} placeholder={words.search}
              aria-label={words.search} onChange={(e) => setQuery(e.target.value)} />
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
            {shown.length === 0 && <li className="muted">{words.none}</li>}
          </ul>
          <span className="hint">{tn(chosen.length, ...words.chosen)}</span>
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
          {run.dry_run ? t('Simulazione') : t('Import')} · {scopeOf(run)}
        </span>
        <span className="muted">
          {[run.source_version ? `${sourceLabel(run.source)} ${run.source_version}` : sourceLabel(run.source), run.requested_by,
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

const EMPTY = { url: '', token: '', username: '', app_token: '', verify_tls: true, default_site: '' }

/** Connessione all'ultima importazione di questa sorgente (indirizzo, utente, certificato, sede predefinita). */
function lastConnection(runs, source) {
  const last = runs.find((r) => r.source === source)
  if (!last) return EMPTY
  return { ...EMPTY, url: last.url, username: last.username || '', verify_tls: last.verify_tls, default_site: last.default_site || '' }
}

export default function ImportPage() {
  const { data: runs, error: runsError, reload: reloadRuns } = useApi('/imports')
  const [params, setParams] = useSearchParams()
  const sourceKey = sourceOf(params.get('source'))?.key ?? null
  const source = sourceOf(sourceKey)
  const [conn, setConn] = useState(EMPTY)
  const [probe, setProbe] = useState(null)
  const [chosen, setChosen] = useState(null) // null = tutte le sedi (o tutti i gruppi)
  const [busy, setBusy] = useState(null) // 'test' | 'dry' | 'real'
  const [error, setError] = useState(null)
  const [openId, setOpenId] = useState(null)
  const [run, setRun] = useState(null)
  const [csvOpen, setCsvOpen] = useState(false)
  const started = useRef(false)

  const setField = (name, value) => {
    setConn((prev) => ({ ...prev, [name]: value }))
    if (name !== 'default_site') {
      setProbe(null) // un'altra connessione: gruppi e numeri vanno riletti
      setChosen(null)
    }
  }

  const chooseSource = (key) => {
    setParams(key ? { source: key } : {}, { replace: true })
  }

  // Cambiando sorgente riparto dai dati della sua ultima importazione
  useEffect(() => {
    if (!runs) return
    setConn(lastConnection(runs, sourceKey))
    setProbe(null)
    setChosen(null)
    setError(null)
  }, [sourceKey]) // eslint-disable-line react-hooks/exhaustive-deps

  // All'apertura: se c'è un import in corso lo mostro; senza sorgente scelta riprendo quella dell'ultimo
  useEffect(() => {
    if (!runs || started.current) return
    started.current = true
    if (runs.length && active(runs[0])) setOpenId(runs[0].id)
    if (!sourceKey && runs.length) chooseSource(runs[0].source)
    else setConn(lastConnection(runs, sourceKey))
  }, [runs]) // eslint-disable-line react-hooks/exhaustive-deps

  const loadRun = useCallback(async (id) => {
    try {
      setRun(await api.get(`/imports/${id}`))
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

  const connection = () => ({
    source: sourceKey,
    url: conn.url,
    token: conn.token,
    username: source.username ? conn.username : null,
    app_token: source.appToken ? conn.app_token : null,
    verify_tls: conn.verify_tls,
  })

  const test = async (e) => {
    e.preventDefault()
    setBusy('test')
    setError(null)
    setProbe(null)
    try {
      setProbe(await api.post('/imports/test', connection()))
    } catch (err) {
      setError(err)
    } finally {
      setBusy(null)
    }
  }

  const start = async (dryRun) => {
    if (!dryRun && !window.confirm(t('Importare da {source}? Gli oggetti che mancano vengono creati in NetMap; quelli che ci sono già restano come sono.', { source: source.label }))) return
    setBusy(dryRun ? 'dry' : 'real')
    setError(null)
    try {
      const created = await api.post('/imports', {
        ...connection(), group_ids: chosen ?? [], dry_run: dryRun,
        default_site: source.defaultSite ? conn.default_site : null,
      })
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
  const noGroups = chosen !== null && chosen.length === 0
  const remote = source && source.key !== 'csv'
  const missing = !conn.token.trim() || (!source?.url?.optional && !conn.url.trim()) || (source?.username?.required && !conn.username.trim())

  return (
    <div className="page netbox-page">
      <header className="page-head">
        <div>
          <h1>{t('Import')}</h1>
          <p className="page-intro">
            {t('Porta in NetMap i device (e quello che c\'è intorno) da un file o da un altro programma. Dagli altri programmi si crea solo quello che manca: gli oggetti che ci sono già in NetMap, con lo stesso nome, restano come sono. Prova prima con la simulazione.')}
          </p>
        </div>
      </header>

      <section className="section">
        <header className="section__head"><h2>{t('Da dove')}</h2></header>
        <div className="form__grid">
          <div className="field">
            <label className="field__label" htmlFor="import-source">{t('Sorgente')}</label>
            <select id="import-source" className="input" value={sourceKey ?? ''} onChange={(e) => chooseSource(e.target.value)}>
              <option value="" disabled>{t('Scegli da dove importare…')}</option>
              {IMPORT_SOURCES.map((s) => <option key={s.key} value={s.key}>{s.label}</option>)}
            </select>
          </div>
        </div>
        {source && <p className="hint netbox-note">{source.intro}</p>}
        {source?.key === 'csv' && (
          <div className="update-actions">
            <button type="button" className="btn btn--primary" onClick={() => setCsvOpen(true)}>
              <Icon name="upload" /> {t('Scegli il file da importare')}
            </button>
          </div>
        )}
      </section>

      {remote && (
        <form className="form" onSubmit={test}>
          <section className="section">
            <header className="section__head"><h2>{t('Connessione')}</h2></header>
            <div className="form__grid">
              <TextField label={source.url.label} value={conn.url} onChange={(v) => setField('url', v)} required={!source.url.optional}
                placeholder={source.url.placeholder} hint={source.url.hint} />
              {source.username && (
                <TextField label={t('Utente')} value={conn.username} onChange={(v) => setField('username', v)}
                  required={source.username.required} hint={source.username.hint} />
              )}
              <TextField label={source.token.label} type="password" value={conn.token} onChange={(v) => setField('token', v)} required
                hint={[source.token.hint, SAVED].filter(Boolean).join(' ')} />
              {source.appToken && (
                <TextField label={t('App-Token')} type="password" value={conn.app_token} onChange={(v) => setField('app_token', v)}
                  hint={source.appToken.hint} />
              )}
              <div className="field field--wide">
                <label className="check">
                  <input type="checkbox" checked={conn.verify_tls} onChange={(e) => setField('verify_tls', e.target.checked)} />
                  {t('Verifica il certificato HTTPS')}
                </label>
                {!conn.verify_tls && <span className="hint">{t('Spegnila solo se il server ha un certificato autofirmato: i dati passano comunque cifrati.')}</span>}
              </div>
            </div>
            <div className="update-actions netbox-actions">
              <button type="submit" className="btn" disabled={busy !== null || missing}>
                <Icon name="key" /> {busy === 'test' ? t('Prova in corso…') : t('Prova la connessione')}
              </button>
            </div>
          </section>
        </form>
      )}

      <ErrorBox error={error} />

      {remote && probe && (
        <section className="section">
          <header className="section__head"><h2>{t('Cosa importare')}</h2></header>
          <p className="notice">
            {t('Connesso a {source} {version}: {counts}.', {
              source: source.label,
              version: probe.version,
              counts: source.key === 'netbox'
                ? COUNTS.map(([key, one, many]) => tn(probe.counts[key] ?? 0, one, many)).join(', ')
                : [tn(probe.counts.devices ?? 0, '1 device', '{n} device'), tn(probe.counts.groups ?? 0, ...source.groups.count)].join(', '),
            })}
          </p>
          <GroupPicker groups={probe.groups} words={source.groups} chosen={chosen} setChosen={setChosen} />
          {source.defaultSite && (
            <div className="form__grid netbox-default-site">
              <TextField label={t('Sede per i device senza sede')} value={conn.default_site} onChange={(v) => setField('default_site', v)}
                placeholder={source.label} hint={t('Se manca in NetMap viene creata. Vuoto = una sede con il nome del programma.')} />
            </div>
          )}
          <p className="hint netbox-note">
            {source.note || t('I device che ci sono già in NetMap (stesso nome nella stessa sede) restano come sono, con le loro porte. L\'IP di management va sulla porta che ce l\'ha; se il programma non lo dice, su una porta "mgmt".')}
          </p>
          <div className="update-actions">
            <button type="button" className="btn" disabled={busy !== null || someoneRunning || noGroups} onClick={() => start(true)}>
              <Icon name="play" /> {busy === 'dry' ? t('Avvio…') : t("Simula l'import")}
            </button>
            <button type="button" className="btn btn--primary" disabled={busy !== null || someoneRunning || noGroups} onClick={() => start(false)}>
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
          <div className="empty"><p>{t('Nessun import da altri programmi finora.')}</p></div>
        ) : (
          <div className="table-wrap">
            <table className="table table--dense">
              <thead>
                <tr>
                  <th>{t('Avviato')}</th>
                  <th>{t('Sorgente')}</th>
                  <th>{t('Tipo')}</th>
                  <th>{t('Stato')}</th>
                  <th>{t('Cosa')}</th>
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
                    <td>{sourceLabel(r.source)}</td>
                    <td>{r.dry_run ? t('Simulazione') : t('Import')}</td>
                    <td><RunStatus run={r} /></td>
                    <td>{scopeOf(r)}</td>
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

      {csvOpen && <DeviceImportDialog onClose={() => setCsvOpen(false)} onImported={() => invalidate()} />}
    </div>
  )
}
