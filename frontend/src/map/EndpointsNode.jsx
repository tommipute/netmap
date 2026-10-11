import { memo } from 'react'
import { Link } from 'react-router-dom'
import { t, tn } from '../i18n'
import { shortPortName } from './ports'

// Scheda con gli endpoint (tabelle MAC) di un device, accanto a lui: misure usate anche da MapEditor per la
// disposizione e per le bolle delle posizioni
export const CARD_WIDTH = 210
export const CARD_GAP = 28
export const CARD_ROWS = 6
const HEAD_H = 26
const ROW_H = 19

export function cardHeight(count) {
  const rows = Math.min(count, CARD_ROWS)
  return HEAD_H + rows * ROW_H + (count > CARD_ROWS ? ROW_H : 0) + 6
}

/** Nome da mostrare: quello del device che lo conosce, altrimenti IP, altrimenti MAC. */
export function endpointName(e) {
  return e.known_as || (e.ip ? e.ip.split('/')[0] : e.mac)
}

function EndpointsNode({ data }) {
  const { items, side, deviceId, selectedId, onSelect } = data
  const more = items.length - CARD_ROWS
  return (
    <div className={`epcard epcard--${side}`}>
      <div className="epcard__head">{tn(items.length, '1 endpoint', '{n} endpoint')}</div>
      <ul className="epcard__list">
        {items.slice(0, CARD_ROWS).map((e) => (
          <li key={e.id}>
            <button type="button" className={`epcard__row nodrag${e.id === selectedId ? ' is-selected' : ''}`}
              onClick={(ev) => {
                ev.stopPropagation()
                onSelect(e.id)
              }}
              title={`${e.interface_name || ''} · ${e.mac}${e.ip ? ` · ${e.ip}` : ''}`}>
              <span className="epcard__port mono">{shortPortName(e.interface_name) || '—'}</span>
              <span className={`epcard__name${e.known_as ? '' : ' mono'}`}>{endpointName(e)}</span>
              {e.macs_on_port > 1 && (
                <span className="epcard__many" title={t('{n} MAC su questa porta (switch o access point non documentato?)', { n: e.macs_on_port })}>
                  ×{e.macs_on_port}
                </span>
              )}
            </button>
          </li>
        ))}
      </ul>
      {more > 0 && (
        <Link className="epcard__more nodrag" to={`/where?device_id=${deviceId}`}>{tn(more, 'e un altro', 'e altri {n}')}</Link>
      )}
    </div>
  )
}

export default memo(EndpointsNode)
