import { useVersion } from '../hooks'
import { formatDateTime } from '../options'
import { VERSION } from '../version'
import { t } from '../i18n'

// Licenza AGPL: chi usa NetMap via rete deve poter avere il codice della versione che sta usando
export const SOURCE_URL = 'https://github.com/tommipute/netmap'

/** Un file del repository nella versione installata (tag o commit; in sviluppo main), es. il manuale. */
export const repoFileUrl = (info, path) => `${SOURCE_URL}/blob/${info?.tag || info?.commit || 'main'}/${path}`

/** "NetMap 2026.10.08-2 · a1b2c3d · Codice sorgente": numero di version.js, commit installato e link al codice. */
export default function VersionLabel() {
  const info = useVersion()
  const ref = info?.tag || info?.commit
  const source = (
    <a href={ref ? `${SOURCE_URL}/tree/${ref}` : SOURCE_URL} target="_blank" rel="noreferrer" title={t('Software libero con licenza AGPL-3.0')}>
      {t('Codice sorgente')}
    </a>
  )
  if (!info?.short) return <>NetMap {VERSION} · {source}</>
  const title = [t('Commit {c}', { c: info.commit }), info.date && formatDateTime(info.date), info.tag && t('Tag {tag}', { tag: info.tag })]
    .filter(Boolean).join(' · ')
  return <>NetMap {VERSION} <span title={title}>· {info.short}</span> · {source}</>
}
