import { memo } from 'react'

/**
 * "Bolla" di un rack in mappa: sta sotto device e cavi e li racchiude (posizione e misure le calcola MapEditor).
 * Il nome sta in MapLabels, sopra i cavi, in uno dei quattro angoli.
 */
function RackNode() {
  return <div className="rack-bubble" />
}

export default memo(RackNode)
