import { useAuth } from '../auth'
import { usePref } from '../prefs'
import { navGroups, navItem } from '../resources'
import { useTheme } from '../theme'
import { LANG, LANGUAGES, setLang, t } from '../i18n'
import Modal from './Modal'

const THEMES = [
  { value: 'system', label: t('Automatico') },
  { value: 'light', label: t('Chiaro') },
  { value: 'dark', label: t('Scuro') },
]
const MENUS = [
  { value: 'side', label: t('A lato') },
  { value: 'top', label: t('In alto') },
]
const PAGE_SIZES = ['25', '50', '100', '200']

function Segmented({ label, options, value, onChange }) {
  return (
    <div className="segmented" role="group" aria-label={label}>
      {options.map((option) => (
        <button key={option.value} type="button" className={`segmented__item${value === option.value ? ' segmented__item--on' : ''}`}
          aria-pressed={value === option.value} onClick={() => value !== option.value && onChange(option.value)}>
          {option.label}
        </button>
      ))}
    </div>
  )
}

/** Preferenze di chi guarda: valgono subito e restano in questo browser. */
export default function PrefsDialog({ onClose }) {
  const { isAdmin } = useAuth()
  const [theme, setTheme] = useTheme()
  const [menu, setMenu] = usePref('menu')
  const [pageSize, setPageSize] = usePref('pageSize')
  const [start, setStart] = usePref('start')
  const groups = navGroups(isAdmin)

  return (
    <Modal title={t('Preferenze')} onClose={onClose}>
      <div className="form prefs">
        <div className="prefs__row">
          <span className="field__label">{t('Tema')}</span>
          <Segmented label={t('Tema')} options={THEMES} value={theme} onChange={setTheme} />
        </div>
        <div className="prefs__row">
          <span className="field__label">{t('Lingua')}</span>
          <Segmented label={t('Lingua')} options={LANGUAGES} value={LANG} onChange={setLang} />
          <span className="hint">{t('Cambiando lingua la pagina si ricarica.')}</span>
        </div>
        <div className="prefs__row">
          <span className="field__label">{t('Menu')}</span>
          <Segmented label={t('Menu')} options={MENUS} value={menu} onChange={setMenu} />
          <span className="hint">{t('Sugli schermi stretti (telefono) il menu sta sempre in alto.')}</span>
        </div>
        <label className="prefs__row">
          <span className="field__label">{t('Pagina iniziale')}</span>
          <select className="input" value={start} onChange={(e) => setStart(e.target.value)}>
            {groups.map((group) => (
              <optgroup key={group.title} label={group.title}>
                {group.items.map(navItem).map((item) => <option key={item.to} value={item.to}>{item.title}</option>)}
              </optgroup>
            ))}
          </select>
          <span className="hint">{t('La pagina che si apre entrando in NetMap o cliccando il logo.')}</span>
        </label>
        <label className="prefs__row">
          <span className="field__label">{t('Righe per pagina')}</span>
          <select className="input" value={pageSize} onChange={(e) => setPageSize(e.target.value)}>
            {PAGE_SIZES.map((n) => <option key={n} value={n}>{n}</option>)}
          </select>
          <span className="hint">{t('Negli elenchi (device, IP, cavi…).')}</span>
        </label>
        <p className="hint">{t('Le preferenze restano in questo browser: su un altro computer si scelgono di nuovo.')}</p>
        <div className="modal__footer">
          <button type="button" className="btn btn--primary" onClick={onClose}>{t('Chiudi')}</button>
        </div>
      </div>
    </Modal>
  )
}
