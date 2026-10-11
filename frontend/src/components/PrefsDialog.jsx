import { useAuth } from '../auth'
import { usePref } from '../prefs'
import { navGroups, navItem } from '../resources'
import { useTheme } from '../theme'
import { LANG, LANGUAGES, setLang, t, tc } from '../i18n'
import Modal from './Modal'

const THEMES = [
  { value: 'system', label: t('Automatico') },
  { value: 'light', label: t('Chiaro') },
  { value: 'dark', label: t('Scuro') },
]
const DENSITIES = [
  { value: 'normal', label: t('Normale') },
  { value: 'compact', label: t('Compatta') },
]
const MENUS = [
  { value: 'side', label: t('A lato') },
  { value: 'top', label: t('In alto') },
]
const SECTIONS = [
  { value: 'one', label: t('Una alla volta') },
  { value: 'all', label: t('Tutte aperte') },
]
const DATES = [
  { value: 'full', label: t('Complete') },
  { value: 'relative', label: t('"3 ore fa"') },
]
const CLOCKS = [
  { value: '24', label: t('24 ore') },
  { value: '12', label: t('12 ore (AM/PM)') },
]
const PAGE_SIZES = ['25', '50', '100', '200']
const REFRESH = [
  { value: '15', label: t('Ogni 15 secondi') },
  { value: '30', label: t('Ogni 30 secondi') },
  { value: '60', label: t('Ogni minuto') },
  { value: '300', label: t('Ogni 5 minuti') },
  { value: '0', label: t('Mai (solo con il pulsante Aggiorna)') },
]
const MAP_BOXES = [
  { name: 'mapLocations', label: t('Posizioni') },
  { name: 'mapEndpoints', label: t('Endpoint') },
  { name: 'mapBackground', label: t('Sfondo') },
]

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

/** Una preferenza: nome, scelta, spiegazione */
function Row({ label, hint, children }) {
  return (
    <div className="prefs__row">
      <span className="field__label">{label}</span>
      {children}
      {hint && <span className="hint">{hint}</span>}
    </div>
  )
}

function MapBox({ name, label }) {
  const [value, setValue] = usePref(name)
  return (
    <label className="check">
      <input type="checkbox" checked={value === '1'} onChange={(e) => setValue(e.target.checked ? '1' : '0')} />
      {label}
    </label>
  )
}

/** Preferenze di chi guarda: valgono subito; per l'utente collegato si salvano sul server. */
export default function PrefsDialog({ onClose }) {
  const { enabled, isAdmin, user } = useAuth()
  const [theme, setTheme] = useTheme()
  const [density, setDensity] = usePref('density')
  const [menu, setMenu] = usePref('menu')
  const [sections, setSections] = usePref('menuSections')
  const [pageSize, setPageSize] = usePref('pageSize')
  const [start, setStart] = usePref('start')
  const [dates, setDates] = usePref('dates')
  const [clock, setClock] = usePref('clock')
  const [refresh, setRefresh] = usePref('refresh')
  const [remember, setRemember] = usePref('mapRemember')
  const groups = navGroups(isAdmin)

  return (
    <Modal title={t('Preferenze')} onClose={onClose} wide>
      <div className="form">
        <div className="prefs">
          <section className="prefs__group">
            <h3>{t('Aspetto')}</h3>
            <Row label={t('Tema')}>
              <Segmented label={t('Tema')} options={THEMES} value={theme} onChange={setTheme} />
            </Row>
            <Row label={t('Densità')} hint={t('Compatta: righe e pulsanti più bassi, più dati sullo schermo.')}>
              <Segmented label={t('Densità')} options={DENSITIES} value={density} onChange={setDensity} />
            </Row>
            <Row label={t('Lingua')} hint={t('Cambiando lingua la pagina si ricarica.')}>
              <Segmented label={t('Lingua')} options={LANGUAGES} value={LANG} onChange={setLang} />
            </Row>
          </section>

          <section className="prefs__group">
            <h3>{t('Menu')}</h3>
            <Row label={tc('menu', 'Posizione')} hint={t('Sugli schermi stretti (telefono) il menu sta sempre in alto.')}>
              <Segmented label={tc('menu', 'Posizione')} options={MENUS} value={menu} onChange={setMenu} />
            </Row>
            {menu === 'side' && (
              <Row label={t('Sezioni')} hint={sections === 'one'
                ? t('Si apre la sezione che clicchi e quella della pagina in cui sei.')
                : t('Tutte le pagine sempre in vista; un clic sul nome chiude la sezione.')}>
                <Segmented label={t('Sezioni')} options={SECTIONS} value={sections} onChange={setSections} />
              </Row>
            )}
            <Row label={t('Pagina iniziale')} hint={t('La pagina che si apre entrando in NetMap o cliccando il logo.')}>
              <select className="input" value={start} onChange={(e) => setStart(e.target.value)} aria-label={t('Pagina iniziale')}>
                {groups.map((group) => (
                  <optgroup key={group.title} label={group.title}>
                    {group.items.map(navItem).map((item) => <option key={item.to} value={item.to}>{item.title}</option>)}
                  </optgroup>
                ))}
              </select>
            </Row>
          </section>

          <section className="prefs__group">
            <h3>{t('Elenchi e date')}</h3>
            <Row label={t('Righe per pagina')} hint={t('Negli elenchi (device, IP, cavi…).')}>
              <select className="input" value={pageSize} onChange={(e) => setPageSize(e.target.value)} aria-label={t('Righe per pagina')}>
                {PAGE_SIZES.map((n) => <option key={n} value={n}>{n}</option>)}
              </select>
            </Row>
            <Row label={t('Date')} hint={t('"3 ore fa" vale per l\'ultima settimana; le date più vecchie restano complete.')}>
              <Segmented label={t('Date')} options={DATES} value={dates} onChange={setDates} />
            </Row>
            <Row label={t('Ora')}>
              <Segmented label={t('Ora')} options={CLOCKS} value={clock} onChange={setClock} />
            </Row>
          </section>

          <section className="prefs__group">
            <h3>{t('Mappa e stato live')}</h3>
            <Row label={t('Accesi all\'apertura della mappa')}>
              <div className="prefs__checks">{MAP_BOXES.map((box) => <MapBox key={box.name} {...box} />)}</div>
            </Row>
            <label className="check">
              <input type="checkbox" checked={remember === '1'} onChange={(e) => setRemember(e.target.checked ? '1' : '0')} />
              {t('Ricorda l\'ultima scelta fatta sulla mappa')}
            </label>
            <Row label={t('Aggiornamento dello stato live')} hint={t('Pallini verdi e rossi in alto e device sulla mappa.')}>
              <select className="input" value={refresh} onChange={(e) => setRefresh(e.target.value)} aria-label={t('Aggiornamento dello stato live')}>
                {REFRESH.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
              </select>
            </Row>
          </section>
        </div>
        <p className="hint">
          {enabled && user
            ? t('Le preferenze sono salvate per il tuo utente: le ritrovi su ogni computer da cui entri.')
            : t('Le preferenze restano in questo browser: su un altro computer si scelgono di nuovo.')}
        </p>
        <div className="modal__footer">
          <button type="button" className="btn btn--primary" onClick={onClose}>{t('Chiudi')}</button>
        </div>
      </div>
    </Modal>
  )
}
