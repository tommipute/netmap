import { memo } from 'react'
import { t } from '../i18n'

/**
 * Bolla di una posizione (edificio, piano, stanza): sta sotto rack, device e cavi e li racchiude; colore per
 * livello (data.depth). Il nome in alto a sinistra seleziona tutti i device della posizione, così si spostano insieme.
 */
function LocationNode({ data }) {
  return (
    <div className={`loc-bubble loc-bubble--d${Math.min(data.depth, 3)}`}>
      <button type="button" className="loc-bubble__label nodrag" onClick={(e) => {
          e.stopPropagation()
          data.onSelect()
        }}
        title={t('{name}: clic per selezionare i suoi device e spostarli insieme', { name: data.path })}>
        {data.name}
      </button>
    </div>
  )
}

export default memo(LocationNode)
