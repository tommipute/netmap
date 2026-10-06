import { Link, useSearchParams } from 'react-router-dom'
import { ErrorBox, Loading, Mono } from '../components/Bits'
import { useApi } from '../hooks'

const GROUPS = [
  { type: 'device', title: 'Device' },
  { type: 'interface', title: 'Porte con questo MAC' },
  { type: 'ip', title: 'Indirizzi IP' },
  { type: 'endpoint', title: "Dov'è collegato (tabelle MAC degli switch)" },
]

export default function SearchPage() {
  const [params] = useSearchParams()
  const q = (params.get('q') || '').trim()
  const { data, error, loading } = useApi(q.length >= 2 ? `/search?q=${encodeURIComponent(q)}` : null)

  return (
    <div className="page">
      <header className="page-head">
        <div>
          <h1>Risultati per "{q}"</h1>
          <p className="page-intro">Cerca per nome o seriale del device, MAC address (anche aabb.ccdd.eeff) o indirizzo IP.</p>
        </div>
      </header>
      <ErrorBox error={error} />
      {loading && <Loading />}
      {data && data.length === 0 && (
        <div className="empty">
          <p>Nessun risultato. Prova con una parte del nome, gli ultimi caratteri del MAC o l'inizio dell'IP.</p>
        </div>
      )}
      {data &&
        GROUPS.map((group) => {
          const items = data.filter((r) => r.type === group.type)
          if (items.length === 0) return null
          return (
            <section key={group.type} className="section">
              <h2>{group.title}</h2>
              <ul className="results">
                {items.map((r) => (
                  <li key={`${r.type}-${r.id}`}>
                    {r.type === 'endpoint' ? (
                      <Link to={`/where?q=${encodeURIComponent(r.label.split(' ')[0])}`}><Mono>{r.label}</Mono></Link>
                    ) : r.device_id ? (
                      <Link to={`/devices/${r.device_id}`}>{r.type === 'device' ? r.label : <Mono>{r.label}</Mono>}</Link>
                    ) : (
                      <Link to="/ip-addresses"><Mono>{r.label}</Mono></Link>
                    )}
                    {r.detail && <span className="results__detail">{r.type === 'interface' ? <Mono>{r.detail}</Mono> : r.type === 'endpoint' ? `collegato a ${r.detail}` : r.detail}</span>}
                  </li>
                ))}
              </ul>
            </section>
          )
        })}
    </div>
  )
}
