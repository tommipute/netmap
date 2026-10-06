import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { qs } from '../api'
import { ErrorBox, Loading, Mono } from '../components/Bits'
import { IconButton } from '../components/Icon'
import { useApi, useDebounced } from '../hooks'
import { formatDateTime, formatSince } from '../options'

const LIMIT = 50

function place(e) {
  return [e.site, e.location, e.rack && `rack ${e.rack}`].filter(Boolean).join(' · ')
}

function vlanText(e) {
  if (e.vlan === null || e.vlan === undefined) return null
  return e.vlan_name ? `${e.vlan} ${e.vlan_name}` : String(e.vlan)
}

/** Risposta in evidenza quando la ricerca trova un solo endpoint. */
function Answer({ e }) {
  return (
    <section className="answer" aria-label="Dove è collegato">
      <p className="answer__what">
        <Mono>{e.mac}</Mono>
        {e.ip && <> · <Mono>{e.ip}</Mono></>}
        {e.known_as && <span className="muted"> · {e.known_as}</span>}
      </p>
      {e.device_id ? (
        <p className="answer__where">
          Collegato a <Link to={`/devices/${e.device_id}`}>{e.device_name}</Link>, porta <Mono>{e.interface_name}</Mono>
          {e.interface_description && <span className="muted"> ({e.interface_description})</span>}
        </p>
      ) : (
        <p className="answer__where">La porta dove era stato visto non esiste più.</p>
      )}
      <dl className="facts facts--inline">
        {place(e) && <div><dt>Dove</dt><dd>{place(e)}</dd></div>}
        {vlanText(e) && <div><dt>VLAN</dt><dd>{vlanText(e)}</dd></div>}
        <div><dt>Visto l'ultima volta</dt><dd>{formatDateTime(e.last_seen_at)}</dd></div>
        <div><dt>Visto la prima volta</dt><dd>{formatDateTime(e.first_seen_at)}</dd></div>
      </dl>
      {e.macs_on_port > 1 && (
        <p className="notice notice--warn">
          Su questa porta si vedono {e.macs_on_port} MAC: probabilmente dietro c'è un telefono IP, uno switch non gestito o un access point.
        </p>
      )}
      {e.previous_device_name && (
        <p className="hint">
          Prima era su {e.previous_device_name} <Mono>{e.previous_interface_name}</Mono> (spostato {formatSince(e.moved_at)}).
        </p>
      )}
    </section>
  )
}

export default function EndpointsPage() {
  const [params, setParams] = useSearchParams()
  const [search, setSearch] = useState(params.get('q') || '')
  const [offset, setOffset] = useState(0)
  const q = useDebounced(search.trim())
  const deviceId = params.get('device_id')
  const interfaceId = params.get('interface_id')

  // La ricerca resta nell'indirizzo: si può condividere il link
  useEffect(() => {
    setParams((prev) => {
      const next = new URLSearchParams(prev)
      if (q) next.set('q', q)
      else next.delete('q')
      return next
    }, { replace: true })
    setOffset(0)
  }, [q, setParams])

  const { data, error, loading } = useApi(
    `/endpoints${qs({ q, device_id: deviceId, interface_id: interfaceId, limit: LIMIT, offset })}`,
  )
  const scoped = Boolean(deviceId || interfaceId)

  return (
    <div className="page">
      <header className="page-head">
        <div>
          <h1>Dov'è collegato?</h1>
          <p className="page-intro">
            Cerca un PC, una stampante o un telefono per MAC address, IP o nome DNS: trovi lo switch e la porta a cui è attaccato.
            I dati arrivano dalle tabelle MAC e ARP lette dalle scansioni SNMP.
          </p>
        </div>
      </header>

      <div className="toolbar">
        <input
          type="search"
          className="input toolbar__search toolbar__search--wide"
          placeholder="MAC, IP o nome DNS (es. 00:50:56, aabb.ccdd.eeff, 10.1.2.)"
          value={search}
          autoFocus
          aria-label="Cerca per MAC, IP o nome DNS"
          onChange={(e) => setSearch(e.target.value)}
        />
        {scoped && (
          <button type="button" className="btn btn--ghost btn--sm" onClick={() => setParams(q ? { q } : {})}>
            Mostra tutte le porte
          </button>
        )}
        {data && <span className="toolbar__count">{data.total === 1 ? '1 endpoint' : `${data.total} endpoint`}</span>}
      </div>

      <ErrorBox error={error} />
      {!data && loading && <Loading />}

      {data && data.total === 0 && (
        <div className="empty">
          {q || scoped ? (
            <p>Nessun endpoint trovato. Prova con gli ultimi caratteri del MAC o l'inizio dell'IP.</p>
          ) : (
            <p>
              Ancora nessun endpoint. Compaiono dopo una scansione SNMP degli switch (tabelle MAC) e dei router o switch L3
              (tabelle ARP): avviala da <Link to="/discovery-jobs">Scansioni</Link>.
            </p>
          )}
        </div>
      )}

      {data && data.items.length === 1 && (q || interfaceId) && <Answer e={data.items[0]} />}

      {data && data.items.length > 0 && (
        <div className="table-wrap">
          <table className="table table--dense">
            <thead>
              <tr>
                <th>MAC</th>
                <th>IP</th>
                <th>Switch e porta</th>
                <th>VLAN</th>
                <th>Dove</th>
                <th>Ultima volta</th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((e) => (
                <tr key={e.id}>
                  <td>
                    <Mono>{e.mac}</Mono>
                    {e.known_as && <div className="hint">{e.known_as}</div>}
                  </td>
                  <td><Mono>{e.ip}</Mono></td>
                  <td>
                    {e.device_id ? (
                      <>
                        <Link to={`/devices/${e.device_id}`}>{e.device_name}</Link> <Mono>{e.interface_name}</Mono>
                        {e.macs_on_port > 1 && <span className="tag" title="MAC visti su questa porta">{e.macs_on_port} MAC</span>}
                      </>
                    ) : (
                      <span className="muted">porta eliminata</span>
                    )}
                    {e.previous_device_name && (
                      <div className="hint">prima: {e.previous_device_name} {e.previous_interface_name}</div>
                    )}
                  </td>
                  <td>{vlanText(e) || <span className="muted">—</span>}</td>
                  <td>{place(e) || <span className="muted">—</span>}</td>
                  <td>{formatDateTime(e.last_seen_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {data && data.total > LIMIT && (
        <div className="pager">
          <IconButton icon="prev" label="Pagina precedente" small className="btn--ghost" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - LIMIT))} />
          <span>{offset + 1}–{Math.min(offset + LIMIT, data.total)} di {data.total}</span>
          <IconButton icon="next" label="Pagina successiva" small className="btn--ghost" disabled={offset + LIMIT >= data.total} onClick={() => setOffset(offset + LIMIT)} />
        </div>
      )}
    </div>
  )
}
