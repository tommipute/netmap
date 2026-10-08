import { useEffect, useRef } from 'react'
import { createPortal } from 'react-dom'
import { t } from '../i18n'

// Finestre aperte, l'ultima è in primo piano (es. "Nuovo rack" aperto dal menu del modulo del device)
const open = []

export default function Modal({ title, onClose, children, wide = false }) {
  const dialogRef = useRef(null)
  const closeRef = useRef(onClose)
  closeRef.current = onClose

  useEffect(() => {
    const me = {}
    open.push(me)
    const onKey = (e) => e.key === 'Escape' && open[open.length - 1] === me && closeRef.current()
    window.addEventListener('keydown', onKey)
    const first = dialogRef.current?.querySelector('input, select, textarea, button:not(.modal__close)')
    first?.focus()
    return () => {
      window.removeEventListener('keydown', onKey)
      open.splice(open.indexOf(me), 1)
    }
  }, [])

  return createPortal(
    <div className="modal-backdrop" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div ref={dialogRef} className={`modal${wide ? ' modal--wide' : ''}`} role="dialog" aria-modal="true" aria-label={title}>
        <header className="modal__header">
          <h2>{title}</h2>
          <button type="button" className="modal__close" onClick={onClose} aria-label={t('Chiudi')}>
            ×
          </button>
        </header>
        {children}
      </div>
    </div>,
    document.body,
  )
}
