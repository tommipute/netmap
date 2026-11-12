/**
 * Animazioni dell'interfaccia: brevi, solo transform e opacity, quando qualcosa compare (pagina, righe, finestre,
 * menu), mai agli aggiornamenti automatici. Quasi tutte stanno in fondo a styles.css; qui ci sono quelle che hanno
 * bisogno di JavaScript. "Animazioni: Ridotte" nelle Preferenze o il movimento ridotto chiesto dal sistema operativo
 * le spengono: il CSS legge data-motion su <html> (lo scrive applyDocument in storage.js).
 */
import { useEffect, useRef, useState } from 'react'
import { flushSync } from 'react-dom'
import { applyDocument, readLocal } from './storage'

const reducedMedia = window.matchMedia('(prefers-reduced-motion: reduce)')
reducedMedia.addEventListener('change', applyDocument)

/** true = niente movimento (scelta dell'utente o del sistema operativo). */
export const calm = () => readLocal('netmap.motion') === 'reduced' || reducedMedia.matches

/**
 * Applica un cambio dell'aspetto (il tema) con un cerchio che cresce dal punto (x, y) fino a coprire lo schermo.
 * Senza View Transitions nel browser, o con il movimento ridotto, il cambio è immediato.
 */
export function revealFrom(x, y, change) {
  if (calm() || !document.startViewTransition) {
    change()
    return
  }
  const r = Math.hypot(Math.max(x, window.innerWidth - x), Math.max(y, window.innerHeight - y))
  const transition = document.startViewTransition(() => flushSync(change))
  transition.ready
    .then(() => {
      document.documentElement.animate(
        { clipPath: [`circle(0px at ${x}px ${y}px)`, `circle(${r}px at ${x}px ${y}px)`] },
        { duration: 520, easing: 'cubic-bezier(.4, 0, .2, 1)', pseudoElement: '::view-transition-new(root)' },
      )
    })
    .catch(() => {})
}

/** Numero intero che conta da 0 quando compare e scivola al valore nuovo quando cambia. */
export function CountUp({ value }) {
  const [shown, setShown] = useState(() => (calm() ? value : 0))
  const current = useRef(shown)
  useEffect(() => {
    if (calm() || current.current === value) {
      current.current = value
      setShown(value)
      return undefined
    }
    const from = current.current
    const start = performance.now()
    const duration = Math.min(900, 420 + Math.abs(value - from) * 4)
    let frame = 0
    const step = (now) => {
      const k = Math.min(1, (now - start) / duration)
      const next = from + (value - from) * (1 - (1 - k) ** 3)
      current.current = next
      setShown(next)
      if (k < 1) frame = requestAnimationFrame(step)
    }
    frame = requestAnimationFrame(step)
    return () => cancelAnimationFrame(frame)
  }, [value])
  return Math.round(shown)
}
