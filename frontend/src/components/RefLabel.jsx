import { useOptions } from '../hooks'
import { resources } from '../resources'

/** Mostra il nome di un elemento collegato partendo dal suo id. */
export default function RefLabel({ resource, id, empty = '—' }) {
  const config = resources[resource]
  const items = useOptions(id === null || id === undefined ? null : config.path)
  if (id === null || id === undefined) return <span className="muted">{empty}</span>
  const item = items.find((o) => o.id === id)
  return item ? config.label(item) : <span className="muted">#{id}</span>
}
