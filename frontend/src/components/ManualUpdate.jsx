import { useState } from 'react'
import { copyText } from './SecretInput'
import { SOURCE_URL } from './VersionLabel'
import { readLocal, store } from '../storage'
import { formatDateTime } from '../options'
import { t } from '../i18n'

/**
 * Installazioni senza lo script di aggiornamento (install.kind = manual, vedi services/install.py): da dove viene il
 * codice e i comandi da copiare per aggiornare, in PowerShell su Windows e in bash altrove. Le cartelle scritte qui
 * restano nel browser (e nelle preferenze dell'utente), così i comandi si copiano già pronti.
 */

const DIR_KEY = 'netmap.installDir'
const EXTRACTED_KEY = 'netmap.installExtracted'
const SOURCES = {
  image: t('Immagini pronte'),
  git: t('Codice con git'),
  archive: t('Zip da GitHub'),
}
const HOSTS = {
  windows: t('Docker Desktop su Windows'),
  mac: t('Docker Desktop su Mac'),
  linux: t('Docker su Linux'),
}

/** "Installazione" nella pagina Aggiornamenti: da dove viene il codice, dove gira e chi lo aggiorna. */
export function InstallLabel({ install }) {
  if (!install) return <span className="muted">—</span>
  return (
    <>
      <span><strong>{SOURCES[install.source] || install.source}</strong> · {HOSTS[install.host] || install.host}</span>
      <span className="hint">
        {install.kind === 'server' ? t('aggiornamenti con lo script sul server') : t('aggiornamenti a mano')}
      </span>
    </>
  )
}

const quote = (path, win) => (win || /\s/.test(path) ? `"${path}"` : path)

function commandLines(install, dir, extracted) {
  const win = install.host === 'windows'
  const folder = quote(dir || t('<cartella di NetMap>'), win)
  const backup = [
    `# ${t('Backup del database, in backups nella cartella di NetMap')}`,
    "docker compose exec db sh -c 'pg_dump -U $POSTGRES_USER -d $POSTGRES_DB -Fc -f /tmp/netmap.dump'",
    'docker compose cp db:/tmp/netmap.dump backups/manual-prima-aggiornamento.dump',
  ]
  const lines = [`cd ${folder}`, ...backup]
  if (install.source === 'image') {
    lines.push(`# ${t('Scarica le immagini nuove e riavvia; le migration del database partono da sole')}`,
      'docker compose pull', 'docker compose up -d')
  } else if (install.source === 'archive') {
    const from = quote(extracted || t('<cartella estratta>'), win)
    lines.unshift(`# ${t('Prima scarica lo zip della versione nuova (Source code) da {url} ed estrailo', { url: `${SOURCE_URL}/releases` })}`)
    lines.push(`# ${t('Ferma NetMap: il database resta (mai docker compose down -v)')}`, 'docker compose down',
      `# ${t('Copia i file nuovi sopra i vecchi, senza toccare configurazione e dati')}`,
      win
        ? `robocopy ${from} . /E /XF .env .secrets_key /XD updater-data backups data node_modules`
        : `cp -r ${from}/. .`,
      `# ${t('Ricostruisce e riavvia; le migration del database partono da sole')}`, 'docker compose up -d --build')
  } else {
    lines.push(`# ${t('Scarica la versione nuova (se git si ferma per modifiche tue: git stash, poi di nuovo git pull)')}`,
      'git pull',
      `# ${t('Ricostruisce e riavvia; le migration del database partono da sole')}`, 'docker compose up -d --build')
  }
  return lines.join('\n')
}

export default function ManualUpdate({ install }) {
  const win = install.host === 'windows'
  const [dir, setDir] = useState(() => readLocal(DIR_KEY) || '')
  const [extracted, setExtracted] = useState(() => readLocal(EXTRACTED_KEY) || '')
  const [copied, setCopied] = useState(false)
  const text = commandLines(install, dir.trim(), extracted.trim())

  const save = (key, setter) => (e) => {
    setter(e.target.value)
    store(key, e.target.value.trim() || null)
    setCopied(false)
  }
  const copy = async () => {
    try {
      await copyText(text)
      setCopied(true)
    } catch {
      setCopied(false)
    }
  }

  return (
    <section className="section manual-update">
      <header className="section__head"><h2>{t('Come aggiornare')}</h2></header>
      {install.stale_updater && (
        <p className="notice notice--warn">
          {t("Lo script di aggiornamento ha girato l'ultima volta il {when}: se su questo server deve aggiornare NetMap, controlla il timer con systemctl status netmap-updater.timer.", { when: formatDateTime(install.updater_last_run) })}
        </p>
      )}
      <p className="hint">
        {t("NetMap è installato senza lo script di aggiornamento: si aggiorna a mano, con i comandi qui sotto. Le versioni nuove e le loro novità sono su GitHub:")}{' '}
        <a href={`${SOURCE_URL}/releases`} target="_blank" rel="noreferrer">{t('versioni di NetMap')}</a>.
      </p>
      <div className="form__grid">
        <label className="field">
          <span className="field__label">{t('Cartella di NetMap')}</span>
          <input className="input" value={dir} onChange={save(DIR_KEY, setDir)} placeholder={win ? 'C:\\NetMap' : '/opt/netmap'} />
          <span className="hint">{t('Quella con docker-compose.yml e il file .env.')}</span>
        </label>
        {install.source === 'archive' && (
          <label className="field">
            <span className="field__label">{t('Cartella estratta dallo zip')}</span>
            <input className="input" value={extracted} onChange={save(EXTRACTED_KEY, setExtracted)}
              placeholder={win ? 'C:\\Users\\nome\\Downloads\\netmap-1.2.1' : '~/Downloads/netmap-1.2.1'} />
            <span className="hint">{t('Anche qui, quella che contiene docker-compose.yml.')}</span>
          </label>
        )}
      </div>
      <div>
        <p className="field__label">{win ? t('Comandi per PowerShell') : t('Comandi per il terminale')}</p>
        <pre className="log">{text}</pre>
      </div>
      <div className="update-actions">
        <button type="button" className="btn btn--primary" onClick={copy}>{t('Copia i comandi')}</button>
        {copied && <span className="hint">{t('Copiati negli appunti.')}</span>}
      </div>
      {install.source === 'git' && install.host === 'linux' && (
        <p className="hint">
          {t('Su un server Linux lo script di aggiornamento fa tutto questo da solo, anche in automatico e con il ritorno alla versione di prima se qualcosa va storto: sudo updater/install.sh nella cartella di NetMap (README, «Aggiornamenti automatici»).')}
        </p>
      )}
    </section>
  )
}
