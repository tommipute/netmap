// Dettagli di una porta letti dal monitor: stato e da quando, duplex, errori, PoE
import { formatDateTime, formatPower, formatSince, labelOf, POE_STATUS, recentErrors } from '../options'
import { t } from '../i18n'

/** Pallino su/giù con "da quando" nel tooltip, e "spenta" se è spenta nella configurazione */
export function PortDot({ port }) {
  if (!port.oper_status) return null
  const up = port.oper_status === 'up'
  const since = port.oper_changed_at ? ` (${formatSince(port.oper_changed_at)})` : ''
  return (
    <span className={`oper-dot oper-dot--${up ? 'up' : 'down'}`}
      title={(up ? t("Stato all'ultimo controllo: su") : t("Stato all'ultimo controllo: giù")) + since} />
  )
}

export function AdminDownTag({ port }) {
  if (port.admin_status !== 'down') return null
  return <span className="tag" title={t('Spenta nella configurazione dello switch (shutdown)')}>{t('spenta')}</span>
}

/** Per l'elenco delle porte: "Su" / "Giù da 40 giorni" */
export function PortState({ port }) {
  if (!port.oper_status) return <span className="muted">—</span>
  const up = port.oper_status === 'up'
  return (
    <span className="nowrap">
      <PortDot port={port} />
      {up ? t('Su') : t('Giù')}
      {!up && port.oper_changed_at && <span className="muted"> {formatSince(port.oper_changed_at)}</span>}
      <AdminDownTag port={port} />
    </span>
  )
}

export function DuplexTag({ port }) {
  if (port.duplex !== 'half') return null
  return (
    <span className="badge badge--warn port-flag" title={t('La porta lavora in half duplex: di solito è un problema di cavo o di negoziazione')}>
      {t('half duplex')}
    </span>
  )
}

/** Contatori di errori: in evidenza se sono saliti nelle ultime 24 ore */
export function PortErrors({ port, quiet = false }) {
  const total = (port.in_errors || 0) + (port.out_errors || 0)
  if (port.in_errors === null || port.in_errors === undefined) return quiet ? null : <span className="muted">—</span>
  const title = t('Errori ricevuti {i}, inviati {o}; pacchetti scartati in entrata {din}, in uscita {dout}', {
    i: port.in_errors ?? 0, o: port.out_errors ?? 0, din: port.in_discards ?? 0, dout: port.out_discards ?? 0,
  }) + (port.errors_at ? ' · ' + t('ultimo aumento: {when}', { when: formatDateTime(port.errors_at) }) : '')
  if (recentErrors(port)) {
    return <span className="badge badge--danger port-flag" title={title}>{t('errori in aumento')}</span>
  }
  if (quiet) return null
  return <span className={total ? '' : 'muted'} title={title}>{total.toLocaleString()}</span>
}

/** PoE della porta: consumo, classe o stato */
export function PortPoe({ port }) {
  if (!port.poe_status) return <span className="muted">—</span>
  if (port.poe_status === 'fault') return <span className="badge badge--danger">{t('Guasto')}</span>
  if (port.poe_status === 'searching') {
    return <span className="muted" title={t('Pronta ad alimentare, ma non c\'è niente collegato che lo chieda')}>{t('In attesa')}</span>
  }
  if (port.poe_status !== 'delivering') return <span className="muted">{labelOf(POE_STATUS, port.poe_status)}</span>
  const cls = port.poe_class !== null && port.poe_class !== undefined ? t('classe {n}', { n: port.poe_class }) : null
  return (
    <span className="nowrap" title={t('Il dispositivo collegato è alimentato dallo switch')}>
      {port.poe_power_mw ? formatPower(port.poe_power_mw) : t('Alimenta')}
      {cls && <span className="muted"> · {cls}</span>}
    </span>
  )
}
