import { useVersion } from '../hooks'
import { formatDateTime } from '../options'
import { VERSION } from '../version'
import { t } from '../i18n'

/** "NetMap 2026.10.08-2 · a1b2c3d": numero di version.js più il commit installato (se l'updater l'ha scritto). */
export default function VersionLabel() {
  const info = useVersion()
  if (!info?.short) return <>NetMap {VERSION}</>
  const title = [t('Commit {c}', { c: info.commit }), info.date && formatDateTime(info.date), info.tag && t('Tag {tag}', { tag: info.tag })]
    .filter(Boolean).join(' · ')
  return <>NetMap {VERSION} <span title={title}>· {info.short}</span></>
}
