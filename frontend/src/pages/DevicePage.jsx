import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api } from '../api'
import { useAuth } from '../auth'
import { Badge, ErrorBox, LiveStatus, Loading, Mono } from '../components/Bits'
import BulkPortsDialog from '../components/BulkPortsDialog'
import CableDialog from '../components/CableDialog'
import RefLabel from '../components/RefLabel'
import ResourceForm from '../components/ResourceForm'
import { invalidate, useApi } from '../hooks'
import { DEVICE_STATUS, INTERFACE_TYPES, SOURCES, formatDateTime, formatSpeed, labelOf } from '../options'

function vlanText(port) {
  if (port.mode === 'access') return port.untagged_vlan ? String(port.untagged_vlan) : '—'
  if (port.mode === 'trunk') {
    const tagged = port.tagged_vlans.length ? port.tagged_vlans.join(', ') : 'nessuna'
    return `Trunk ${tagged}${port.untagged_vlan ? ` (nativa ${port.untagged_vlan})` : ''}`
  }
  return '—'
}

/** Carica l'interfaccia completa e apre il modulo di modifica. */
function EditPort({ portId, onClose, onSaved }) {
  const { data, error } = useApi(`/interfaces/${portId}`)
  useEffect(() => {
    if (error) {
      window.alert(error.message)
      onClose()
    }
  }, [error, onClose])
  if (!data) return null
  return <ResourceForm resourceKey="interfaces" item={data} onClose={onClose} onSaved={onSaved} />
}

export default function DevicePage() {
  const { id } = useParams()
  const navigate = useNavigate()
  const { data: device, error, reload } = useApi(`/devices/${id}`)
  const { data: ports, error: portsError, reload: reloadPorts } = useApi(`/devices/${id}/ports`)
  const { data: pending } = useApi(`/discovery-changes?device_id=${id}&limit=1`)
  const [dialog, setDialog] = useState(null)
  const [checking, setChecking] = useState(false)
  const { canEdit } = useAuth()

  const refresh = () => {
    setDialog(null)
    reload()
    reloadPorts()
  }

  const run = async (question, action) => {
    if (question && !window.confirm(question)) return
    try {
      await action()
      invalidate()
      reloadPorts()
    } catch (err) {
      window.alert(err.message)
    }
  }

  const removeDevice = () =>
    run(`Eliminare ${device.name}? Verranno eliminate anche le sue porte e i cavi collegati.`, async () => {
      await api.del(`/devices/${id}`)
      navigate('/devices')
    })

  const checkNow = async () => {
    setChecking(true)
    try {
      await api.post(`/devices/${id}/check`)
      reload()
      reloadPorts()
    } catch (err) {
      window.alert(err.message)
    } finally {
      setChecking(false)
    }
  }

  if (error) return <div className="page"><ErrorBox error={error} /></div>
  if (!device) return <div className="page"><Loading /></div>

  const primary = ports?.flatMap((p) => p.ips.map((ip) => ({ ...ip, port: p.name }))).find((ip) => ip.is_primary)
  const connected = ports?.filter((p) => p.cable_id).length ?? 0
  const customEntries = Object.entries(device.custom_fields || {})

  return (
    <div className="page">
      <header className="page-head">
        <div>
          <p className="crumbs">
            <Link to="/devices">Device</Link>
          </p>
          <h1 className="device-title">
            {device.name}
            <Badge value={device.status} options={DEVICE_STATUS} />
          </h1>
          <p className="page-intro">
            <RefLabel resource="device-roles" id={device.role_id} empty="Nessun ruolo" />
            {', '}
            <RefLabel resource="device-types" id={device.device_type_id} empty="modello non indicato" />
          </p>
        </div>
        <div className="page-head__actions">
          {canEdit && primary && (
            <button type="button" className="btn" onClick={checkNow} disabled={checking} title="Ping e SNMP sull'IP di management">
              {checking ? 'Controllo…' : 'Controlla ora'}
            </button>
          )}
          {canEdit && <button type="button" className="btn" onClick={() => setDialog({ kind: 'edit' })}>Modifica</button>}
          {canEdit && <button type="button" className="btn btn--ghost btn--danger" onClick={removeDevice}>Elimina</button>}
        </div>
      </header>

      {pending?.total > 0 && (
        <p className="notice">
          La scansione SNMP ha {pending.total === 1 ? '1 modifica' : `${pending.total} modifiche`} da approvare per questo device.{' '}
          <Link to={`/discovery/changes?device_id=${device.id}`}>Rivedile</Link>
        </p>
      )}

      <dl className="facts">
        <div><dt>Sede</dt><dd><RefLabel resource="sites" id={device.site_id} /></dd></div>
        <div><dt>Posizione</dt><dd><RefLabel resource="locations" id={device.location_id} /></dd></div>
        <div>
          <dt>Rack</dt>
          <dd>
            {device.rack_id ? (
              <Link to={`/racks/${device.rack_id}`}><RefLabel resource="racks" id={device.rack_id} /></Link>
            ) : (
              <RefLabel resource="racks" id={device.rack_id} />
            )}
            {device.rack_position ? `, U${device.rack_position}` : ''}
          </dd>
        </div>
        <div><dt>IP di management</dt><dd>{primary ? <Mono>{primary.address}</Mono> : <span className="muted">—</span>}</dd></div>
        <div>
          <dt>Stato live</dt>
          <dd>
            {device.reachable === null ? (
              <span className="muted">{primary ? 'Non ancora controllato' : 'Serve un IP di management'}</span>
            ) : (
              <LiveStatus device={device} long />
            )}
          </dd>
        </div>
        <div><dt>Numero di serie</dt><dd><Mono>{device.serial}</Mono></dd></div>
        <div><dt>Asset tag</dt><dd><Mono>{device.asset_tag}</Mono></dd></div>
        <div><dt>Origine dati</dt><dd>{labelOf(SOURCES, device.source)}</dd></div>
        {device.last_seen_at && <div><dt>Ultima scansione</dt><dd>{formatDateTime(device.last_seen_at)}</dd></div>}
        {device.sys_name && device.sys_name !== device.name && <div><dt>sysName</dt><dd><Mono>{device.sys_name}</Mono></dd></div>}
        {customEntries.map(([key, value]) => (
          <div key={key}><dt>{key}</dt><dd>{String(value)}</dd></div>
        ))}
        {device.sys_descr && (
          <div className="facts__wide"><dt>Descrizione SNMP</dt><dd className="hint">{device.sys_descr}</dd></div>
        )}
        {device.description && (
          <div className="facts__wide"><dt>Note</dt><dd>{device.description}</dd></div>
        )}
      </dl>

      <section className="section">
        <header className="section__head">
          <h2>
            Porte
            {ports && <span className="section__count">{ports.length} porte, {connected} collegate</span>}
          </h2>
          <div className="page-head__actions">
            {ports?.some((p) => p.endpoints > 0) && (
              <Link className="btn btn--sm" to={`/where?device_id=${device.id}`}>Endpoint collegati</Link>
            )}
            {canEdit && <button type="button" className="btn btn--sm" onClick={() => setDialog({ kind: 'bulk' })}>Aggiungi in blocco</button>}
            {canEdit && <button type="button" className="btn btn--sm btn--primary" onClick={() => setDialog({ kind: 'port' })}>Aggiungi porta</button>}
          </div>
        </header>
        <ErrorBox error={portsError} />
        {ports && ports.length === 0 && (
          <div className="empty">
            <p>Nessuna porta. Per uno switch usa "Aggiungi in blocco" con un intervallo come Gi1/0/[1-48].</p>
          </div>
        )}
        {ports && ports.length > 0 && (
          <div className="table-wrap">
            <table className="table table--dense">
              <thead>
                <tr>
                  <th>Porta</th>
                  <th>Tipo</th>
                  <th>VLAN</th>
                  <th>Velocità</th>
                  <th>Collegata a</th>
                  <th>IP</th>
                  <th title="MAC visti su questa porta nelle tabelle dello switch">Endpoint</th>
                  <th className="table__actions"><span className="sr-only">Azioni</span></th>
                </tr>
              </thead>
              <tbody>
                {ports.map((p) => (
                  <tr key={p.id} className={p.enabled ? '' : 'is-disabled'}>
                    <td>
                      {p.oper_status && (
                        <span className={`oper-dot oper-dot--${p.oper_status === 'up' ? 'up' : 'down'}`}
                          title={`Stato all'ultimo controllo: ${p.oper_status === 'up' ? 'su' : 'giù'}`} />
                      )}
                      <Mono>{p.name}</Mono>
                      {!p.enabled && <span className="tag">disabilitata</span>}
                    </td>
                    <td>{labelOf(INTERFACE_TYPES, p.type)}</td>
                    <td>{vlanText(p)}</td>
                    <td>{formatSpeed(p.speed_mbps)}</td>
                    <td>
                      {p.cable_id ? (
                        <>
                          <Link to={`/devices/${p.remote_device_id}`}>{p.remote_device}</Link> <Mono>{p.remote_interface}</Mono>
                          {p.cable_status === 'planned' && <span className="tag">pianificato</span>}
                        </>
                      ) : (
                        <span className="muted">—</span>
                      )}
                    </td>
                    <td>
                      {p.ips.length === 0 && <span className="muted">—</span>}
                      {p.ips.map((ip) => (
                        <div key={ip.id}><Mono>{ip.address}</Mono></div>
                      ))}
                    </td>
                    <td>
                      {p.endpoints > 0 ? (
                        <Link to={`/where?interface_id=${p.id}`}>{p.endpoints === 1 ? '1 MAC' : `${p.endpoints} MAC`}</Link>
                      ) : (
                        <span className="muted">—</span>
                      )}
                    </td>
                    <td className="table__actions">
                      {!canEdit ? null : p.cable_id ? (
                        <button type="button" className="btn btn--ghost btn--sm"
                          onClick={() => run(`Scollegare ${p.name} da ${p.remote_device} ${p.remote_interface}?`, () => api.del(`/cables/${p.cable_id}`))}>
                          Scollega
                        </button>
                      ) : (
                        p.cableable && (
                          <button type="button" className="btn btn--ghost btn--sm" onClick={() => setDialog({ kind: 'cable', portId: p.id })}>
                            Collega
                          </button>
                        )
                      )}
                      {canEdit && (
                        <>
                          <button type="button" className="btn btn--ghost btn--sm" onClick={() => setDialog({ kind: 'editPort', portId: p.id })}>
                            Modifica
                          </button>
                          <button type="button" className="btn btn--ghost btn--sm btn--danger"
                            onClick={() => run(`Eliminare la porta ${p.name}?`, () => api.del(`/interfaces/${p.id}`))}>
                            Elimina
                          </button>
                        </>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {dialog?.kind === 'edit' && (
        <ResourceForm resourceKey="devices" item={device} onClose={() => setDialog(null)} onSaved={refresh} />
      )}
      {dialog?.kind === 'port' && (
        <ResourceForm resourceKey="interfaces" preset={{ device_id: device.id }} onClose={() => setDialog(null)} onSaved={refresh} />
      )}
      {dialog?.kind === 'editPort' && <EditPort portId={dialog.portId} onClose={() => setDialog(null)} onSaved={refresh} />}
      {dialog?.kind === 'bulk' && <BulkPortsDialog deviceId={device.id} onClose={() => setDialog(null)} onDone={refresh} />}
      {dialog?.kind === 'cable' && (
        <CableDialog aDeviceId={device.id} aInterfaceId={dialog.portId} onClose={() => setDialog(null)} onCreated={refresh} />
      )}
    </div>
  )
}
