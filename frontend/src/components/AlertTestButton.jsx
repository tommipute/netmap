import { useState } from 'react'
import { api } from '../api'
import { invalidate } from '../hooks'
import { IconButton } from './Icon'

/** Pulsante "Prova" di un canale di avviso: manda un messaggio e dice com'è andata. */
export default function AlertTestButton({ channel, onDone }) {
  const [state, setState] = useState(null) // null | 'sending' | 'ok' | messaggio d'errore
  const test = async (e) => {
    e.stopPropagation()
    setState('sending')
    try {
      await api.post(`/alert-channels/${channel.id}/test`)
      setState('ok')
    } catch (err) {
      setState(err.message)
    }
    invalidate()
    onDone?.()
  }
  return (
    <span className="alert-test" onClick={(e) => e.stopPropagation()}>
      <IconButton icon="play" label="Manda un messaggio di prova" small disabled={state === 'sending'} onClick={test} />
      {state === 'ok' && <span className="live">Inviato</span>}
      {state && state !== 'ok' && state !== 'sending' && <span className="live live--down" title={state}>Non inviato</span>}
    </span>
  )
}
