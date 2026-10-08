import { memo } from 'react'
import { t } from '../i18n'

/**
 * "Bolla" di un rack in mappa: sta sotto device e cavi e li racchiude (posizione e misure le calcola MapEditor).
 * Il nome in basso a sinistra (a destra se lì passa un cavo: data.labelSide) seleziona tutti i device del rack,
 * così si spostano insieme.
 */
function RackNode({ data }) {
  const what = data.count === 1 ? t('1 device') : t('{n} device', { n: data.count })
  return (
    <div className="rack-bubble">
      <button type="button" className={`rack-bubble__label nodrag${data.labelSide === 'right' ? ' rack-bubble__label--right' : ''}`} onClick={(e) => {
          e.stopPropagation()
          data.onSelect()
        }}
        title={t('Rack {name}, {what}: clic per selezionarli e spostarli insieme', { name: data.name, what })}>
        {data.name}
      </button>
    </div>
  )
}

export default memo(RackNode)
