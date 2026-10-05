import { useEffect, useRef } from 'react'
import { createPortal } from 'react-dom'

export default function Modal({ title, onClose, children, wide = false }) {
  const dialogRef = useRef(null)

  useEffect(() => {
    const onKey = (e) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    const first = dialogRef.current?.querySelector('input, select, textarea, button:not(.modal__close)')
    first?.focus()
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  return createPortal(
    <div className="modal-backdrop" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div ref={dialogRef} className={`modal${wide ? ' modal--wide' : ''}`} role="dialog" aria-modal="true" aria-label={title}>
        <header className="modal__header">
          <h2>{title}</h2>
          <button type="button" className="modal__close" onClick={onClose} aria-label="Chiudi">
            ×
          </button>
        </header>
        {children}
      </div>
    </div>,
    document.body,
  )
}
