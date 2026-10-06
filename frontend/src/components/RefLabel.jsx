import { useApi, useOptionsPage } from '../hooks'
import { resources } from '../resources'

/** Mostra il nome di un elemento collegato partendo dal suo id. */
export default function RefLabel({ resource, id, empty = '—' }) {
  const config = resources[resource]
  const hasId = id !== null && id !== undefined
  const { items, total } = useOptionsPage(hasId ? config.path : null)
  const listed = items.find((o) => o.id === id)
  // Oltre il limite dei menu l'elemento può mancare dall'elenco: lo chiedo da solo
  const single = useApi(hasId && !listed && total > items.length ? `/${config.path}/${id}` : null).data
  if (!hasId) return <span className="muted">{empty}</span>
  const item = listed || single
  return item ? config.label(item) : <span className="muted">#{id}</span>
}
