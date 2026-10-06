import { memo } from 'react'

/**
 * "Bolla" di un rack in mappa: sta sotto device e cavi e li racchiude (posizione e misure le calcola MapEditor).
 * Il nome in basso a sinistra seleziona tutti i device del rack, così si spostano insieme.
 */
function RackNode({ data }) {
  const what = data.count === 1 ? '1 device' : `${data.count} device`
  return (
    <div className="rack-bubble">
      <button type="button" className="rack-bubble__label nodrag" onClick={(e) => {
          e.stopPropagation()
          data.onSelect()
        }}
        title={`Rack ${data.name}, ${what}: clic per selezionarli e spostarli insieme`}>
        {data.name}
      </button>
    </div>
  )
}

export default memo(RackNode)
