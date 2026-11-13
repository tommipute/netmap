import { revealFrom } from '../motion'
import { t } from '../i18n'
import { useTheme } from '../theme'
import { Icon } from './Icon'

/** Pulsante tondo chiaro/scuro: il tema nuovo si allarga a cerchio dal pulsante (barra in alto e pagina di accesso). */
export default function ThemeButton({ className = '' }) {
  const [theme, setTheme] = useTheme()
  const dark = theme === 'dark' || (theme === 'system' && window.matchMedia('(prefers-color-scheme: dark)').matches)
  const label = dark ? t('Passa al tema chiaro') : t('Passa al tema scuro')
  const toggle = (e) => {
    const box = e.currentTarget.getBoundingClientRect()
    revealFrom(box.left + box.width / 2, box.top + box.height / 2, () => setTheme(dark ? 'light' : 'dark'))
  }
  return (
    <button type="button" className={`topbar__round ${className}`.trim()} onClick={toggle} title={label} aria-label={label}>
      <Icon name={dark ? 'sun' : 'moon'} size={18} />
    </button>
  )
}
