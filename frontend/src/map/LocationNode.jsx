import { memo } from 'react'

/**
 * Bolla di una posizione (edificio, piano, stanza): sta sotto rack, device e cavi e li racchiude; colore per
 * livello (data.depth). Il nome sta in MapLabels, sopra tutto il resto, in alto a sinistra.
 */
function LocationNode({ data }) {
  return <div className={`loc-bubble loc-bubble--d${Math.min(data.depth, 3)}`} />
}

export default memo(LocationNode)
