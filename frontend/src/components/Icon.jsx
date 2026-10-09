import { Link } from 'react-router-dom'

/**
 * Icone a tratto (24x24, colore del testo). Niente librerie: solo i simboli che servono.
 * IconButton: pulsante con solo l'icona; il testo resta come tooltip e per gli screen reader.
 */
const PATHS = {
  book: <><path d="M4 5h5a3 3 0 0 1 3 3v12a2 2 0 0 0-2-2H4Z" /><path d="M20 5h-5a3 3 0 0 0-3 3v12a2 2 0 0 1 2-2h6Z" /></>,
  edit: <><path d="M4 20h4L19 9a2.8 2.8 0 0 0-4-4L4 16v4Z" /><path d="m13.5 6.5 4 4" /></>,
  trash: <><path d="M4 7h16" /><path d="M10 11v6M14 11v6" /><path d="M5 7l1 13h12l1-13" /><path d="M9 7V4h6v3" /></>,
  upload: <><path d="M12 15V4" /><path d="m7 9 5-5 5 5" /><path d="M4 15v5h16v-5" /></>,
  download: <><path d="M12 4v11" /><path d="m7 10 5 5 5-5" /><path d="M4 15v5h16v-5" /></>,
  print: <><path d="M7 9V3h10v6" /><path d="M7 17H4v-8h16v8h-3" /><path d="M7 14h10v7H7z" /></>,
  link: <><path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1" /><path d="M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1" /></>,
  unlink: <><path d="M15 9.5 18.7 6M9 14.5 5.3 18" /><path d="M13 5.3l.3-.3a4 4 0 0 1 5.7 5.7l-1.6 1.6" /><path d="M11 18.7l-.3.3A4 4 0 0 1 5 13.3l1.6-1.6" /><path d="M3 3l18 18" /></>,
  refresh: <><path d="M20 11a8 8 0 0 0-14.6-4.5L4 8" /><path d="M4 3v5h5" /><path d="M4 13a8 8 0 0 0 14.6 4.5L20 16" /><path d="M20 21v-5h-5" /></>,
  key: <><circle cx="8" cy="15" r="4" /><path d="m11 12 9-9" /><path d="m16 7 3 3" /></>,
  logout: <><path d="M10 4H5v16h5" /><path d="M14 8l4 4-4 4" /><path d="M18 12H9" /></>,
  plus: <path d="M12 5v14M5 12h14" />,
  stack: <><rect x="4" y="4" width="16" height="4.5" rx="1" /><rect x="4" y="10" width="16" height="4.5" rx="1" /><rect x="4" y="16" width="16" height="4" rx="1" /><path d="M7 6.2h.01M7 12.2h.01M7 18h.01" /></>,
  plusMany: <><rect x="8" y="8" width="13" height="13" rx="2" /><path d="M4 16V5a1 1 0 0 1 1-1h11" /><path d="M14.5 11.5v6M11.5 14.5h6" /></>,
  save: <><path d="M5 3h11l4 4v13a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1Z" /><path d="M8 3v5h7V3" /><path d="M8 21v-7h8v7" /></>,
  check: <path d="m5 12 5 5 9-10" />,
  checkAll: <><path d="m2 12 5 5 9-10" /><path d="m12 16 1 1 9-10" /></>,
  play: <path d="M7 4v16l13-8L7 4Z" />,
  log: <><path d="M6 3h9l4 4v14H6z" /><path d="M14 3v5h5" /><path d="M9 12h7M9 16h7" /></>,
  search: <><circle cx="11" cy="11" r="7" /><path d="m20 20-4-4" /></>,
  open: <><path d="M14 4h6v6" /><path d="M20 4 10 14" /><path d="M18 14v6H4V6h6" /></>,
  close: <path d="M6 6l12 12M18 6 6 18" />,
  prev: <path d="m15 6-6 6 6 6" />,
  up: <path d="m6 15 6-6 6 6" />,
  user: <><circle cx="12" cy="8" r="4" /><path d="M4 21a8 8 0 0 1 16 0" /></>,
  down: <path d="m6 9 6 6 6-6" />,
  columns: <><rect x="3.5" y="4" width="17" height="16" rx="2" /><path d="M9.5 4v16M15 4v16" /></>,
  filter: <path d="M4 5h16l-6 7.5V19l-4 1.5v-8L4 5Z" />,
  next: <path d="m9 6 6 6-6 6" />,
  layout: <><rect x="9" y="3" width="6" height="5" rx="1" /><rect x="3" y="16" width="6" height="5" rx="1" /><rect x="15" y="16" width="6" height="5" rx="1" /><path d="M12 8v4M6 16v-4h12v4" /></>,
  eyeOff: <><path d="M3 3l18 18" /><path d="M10.6 6.1A9.8 9.8 0 0 1 12 6c5 0 9 6 9 6a15.6 15.6 0 0 1-2.4 2.9M6.3 7.6C4.2 9.2 3 12 3 12s4 6 9 6a8.6 8.6 0 0 0 3.7-.8" /><path d="M9.9 10a3 3 0 0 0 4.2 4.1" /></>,
}

export function Icon({ name, size = 16 }) {
  return (
    <svg className="icon" width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false">
      {PATHS[name]}
    </svg>
  )
}

/** Come IconButton, ma è un link (apre un'altra pagina). */
export function IconLink({ icon, label, to, small = false, className = '' }) {
  const classes = ['btn', 'btn--icon', small && 'btn--sm', className].filter(Boolean).join(' ')
  return (
    <Link className={classes} to={to} title={label} aria-label={label}>
      <Icon name={icon} />
    </Link>
  )
}

export function IconButton({ icon, label, danger = false, small = false, className = '', children, ...props }) {
  const classes = ['btn', 'btn--icon', small && 'btn--sm', danger && 'btn--danger', className].filter(Boolean).join(' ')
  return (
    <button type="button" className={classes} title={label} aria-label={label} {...props}>
      <Icon name={icon} />
      {children}
    </button>
  )
}
