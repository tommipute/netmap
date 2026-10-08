import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api } from '../api'
import { useAuth } from '../auth'
import { Badge, ErrorBox, LiveStatus, Loading, Mono, PrintFooter } from '../components/Bits'
import BulkPortsDialog from '../components/BulkPortsDialog'
import CableDialog from '../components/CableDialog'
import DeleteDialog from '../components/DeleteDialog'
import HistoryList from '../components/HistoryList'
import { IconButton, IconLink } from '../components/Icon'
import RefLabel from '../components/RefLabel'
import ResourceForm from '../components/ResourceForm'
import { invalidate, useApi } from '../hooks'
import { DEVICE_STATUS, INTERFACE_TYPES, SOURCES, formatDateTime, formatSpeed, labelOf } from '../options'
import { t, tn } from '../i18n'

/** Una VLAN come etichetta: numero e nome (es. "10 UFFICI") */
function VlanTag({ vid, port, native = false }) {
  const name = port.vlan_names?.[vid]
  return (
    <span className={`vlan-tag${native ? ' vlan-tag--native' : ''}`} title={native ? t('Untagged (nativa)') : name || undefined}>
      <span className="mono">{vid}</span>
      {name && <span className="vlan-tag__name">{name}</span>}
    </span>
  )
}

/** Access: la sua VLAN. Trunk: VLAN tagged, più la nativa (untagged) se c'è. */
function PortVlans({ port }) {
  if (port.mode === 'access') {
    return port.untagged_vlan ? <VlanTag vid={port.untagged_vlan} port={port} /> : <span className="muted">—</span>
  }
  if (port.mode === 'trunk') {
    return (
      <div className="vlan-list">
        <span className="tag">{t('trunk')}</span>
        {port.untagged_vlan && <VlanTag vid={port.untagged_vlan} port={port} native />}
        {port.tagged_vlans.map((vid) => <VlanTag key={vid} vid={vid} port={port} />)}
        {port.tagged_vlans.length === 0 && <span className="muted">{t('nessuna tagged')}</span>}
      </div>
    )
  }
  return <span className="muted">—</span>
}

/** Endpoint visti sulla porta: i primi con IP e MAC, poi il link a tutti */
function PortEndpoints({ port }) {
  if (!port.endpoints) return <span className="muted">—</span>
  const more = port.endpoints - port.endpoint_preview.length
  return (
    <div className="endpoint-list">
      {port.endpoint_preview.map((e) => (
        <Link key={e.mac} to={`/where?q=${encodeURIComponent(e.mac)}`} className="endpoint-list__item" title={`MAC ${e.mac}`}>
          <Mono>{e.ip || e.mac}</Mono>
          {e.vlan && <span className="muted"> · VLAN {e.vlan}</span>}
        </Link>
      ))}
      {more > 0 && <Link to={`/where?interface_id=${port.id}`} className="hint">e altri {more}</Link>}
    </div>
  )
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

/** Switch dello stack: un device con più membri (seriale, modello, unità nel rack di ognuno). */
function StackSection({ device, members, canEdit, onAdd, onEdit, onChanged }) {
  const remove = async (m) => {
    if (!window.confirm(t('Togliere il membro {n} dallo stack? Le porte restano.', { n: m.number }))) return
    try {
      await api.del(`/stack-members/${m.id}`)
      onChanged()
    } catch (err) {
      window.alert(err.message)
    }
  }
  return (
    <section className="section">
      <header className="section__head">
        <h2>
          Stack <span className="section__count">{members.length} switch</span>
        </h2>
        {canEdit && (
          <div className="page-head__actions">
            <IconButton icon="plus" label={t('Aggiungi un membro dello stack')} small className="btn--primary" onClick={onAdd} />
          </div>
        )}
      </header>
      <div className="table-wrap">
        <table className="table table--dense">
          <thead>
            <tr>
              <th>{t('Membro')}</th>
              <th>{t('Modello')}</th>
              <th>{t('Numero di serie')}</th>
              <th>{t('Unità')}</th>
              <th>{t('Note')}</th>
              <th className="table__actions"><span className="sr-only">{t('Azioni')}</span></th>
            </tr>
          </thead>
          <tbody>
            {members.map((m) => (
              <tr key={m.id}>
                <td>{m.number}</td>
                <td>{m.model || <span className="muted">—</span>}</td>
                <td><Mono>{m.serial}</Mono></td>
                <td>
                  {m.rack_position ? `U${m.rack_position}` : <span className="muted">{device.rack_id ? '—' : 'device senza rack'}</span>}
                </td>
                <td>{m.description || <span className="muted">—</span>}</td>
                <td className="table__actions">
                  {canEdit && (
                    <>
                      <IconButton icon="edit" label={t('Modifica il membro {n}', { n: m.number })} small className="btn--ghost" onClick={() => onEdit(m)} />
                      <IconButton icon="trash" label={t('Togli il membro {n}', { n: m.number })} small danger className="btn--ghost" onClick={() => remove(m)} />
                    </>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}

/** Ultime modifiche del device, delle sue porte, IP e cavi */
function DeviceHistory({ deviceId }) {
  const { data } = useApi(`/audit-log?device_id=${deviceId}&limit=8`)
  if (!data || data.total === 0) return null
  return (
    <section className="section no-print">
      <header className="section__head">
        <h2>
          {t('Storico')} <span className="section__count">{tn(data.total, '1 modifica', '{n} modifiche')}</span>
        </h2>
        {data.total > data.items.length && (
          <div className="page-head__actions">
            <Link className="btn btn--sm btn--ghost" to={`/history?device_id=${deviceId}`}>{t('Tutto lo storico')}</Link>
          </div>
        )}
      </header>
      <HistoryList entries={data.items} />
    </section>
  )
}

export default function DevicePage() {
  const { id } = useParams()
  const navigate = useNavigate()
  const { data: device, error, reload } = useApi(`/devices/${id}`)
  const { data: ports, error: portsError, reload: reloadPorts } = useApi(`/devices/${id}/ports`)
  const { data: pending } = useApi(`/discovery-changes?device_id=${id}&limit=1`)
  const { data: stack, reload: reloadStack } = useApi(`/stack-members?device_id=${id}&limit=100`)
  const [dialog, setDialog] = useState(null)
  const [checking, setChecking] = useState(false)
  const { canEdit } = useAuth()

  const refresh = () => {
    setDialog(null)
    reload()
    reloadPorts()
    reloadStack()
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

  const removeDevice = () => setDialog({ kind: 'delete' })

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
            <Link to="/devices">{t('Device')}</Link>
          </p>
          <h1 className="device-title">
            {device.name}
            <Badge value={device.status} options={DEVICE_STATUS} />
          </h1>
          <p className="page-intro">
            <RefLabel resource="device-roles" id={device.role_id} empty={t('Nessun ruolo')} />
            {', '}
            <RefLabel resource="device-types" id={device.device_type_id} empty={t('modello non indicato')} />
          </p>
        </div>
        <div className="page-head__actions">
          <IconButton icon="print" label={t('Stampa la scheda')} onClick={() => window.print()} />
          {canEdit && primary && (
            <IconButton icon="refresh" label={checking ? t('Controllo in corso…') : t("Controlla ora (ping e SNMP sull'IP di management)")}
              className={checking ? 'is-spinning' : ''} onClick={checkNow} disabled={checking} />
          )}
          {canEdit && stack?.total === 0 && (
            <IconButton icon="stack" label={t('È uno stack: aggiungi i suoi switch')} onClick={() => setDialog({ kind: 'member' })} />
          )}
          {canEdit && <IconButton icon="edit" label={t('Modifica device')} onClick={() => setDialog({ kind: 'edit' })} />}
          {canEdit && <IconButton icon="trash" label={t('Elimina device')} danger className="btn--ghost" onClick={removeDevice} />}
        </div>
      </header>

      {pending?.total > 0 && (
        <p className="notice no-print">
          {tn(pending.total, 'La scansione SNMP ha 1 modifica da approvare per questo device.', 'La scansione SNMP ha {n} modifiche da approvare per questo device.')}{' '}
          <Link to={`/discovery/changes?device_id=${device.id}`}>{t('Rivedile')}</Link>
        </p>
      )}

      <dl className="facts">
        <div><dt>{t('Sede')}</dt><dd><RefLabel resource="sites" id={device.site_id} /></dd></div>
        <div><dt>{t('Posizione')}</dt><dd><RefLabel resource="locations" id={device.location_id} /></dd></div>
        <div>
          <dt>{t('Rack')}</dt>
          <dd>
            {device.rack_id ? (
              <Link to={`/racks/${device.rack_id}`}><RefLabel resource="racks" id={device.rack_id} /></Link>
            ) : (
              <RefLabel resource="racks" id={device.rack_id} />
            )}
            {device.rack_position ? `, U${device.rack_position}` : ''}
          </dd>
        </div>
        <div><dt>{t('IP di management')}</dt><dd>{primary ? <Mono>{primary.address}</Mono> : <span className="muted">—</span>}</dd></div>
        <div>
          <dt>{t('Stato live')}</dt>
          <dd>
            {device.reachable === null ? (
              <span className="muted">{primary ? t('Non ancora controllato') : t('Serve un IP di management')}</span>
            ) : (
              <LiveStatus device={device} long />
            )}
          </dd>
        </div>
        <div><dt>{t('Numero di serie')}</dt><dd><Mono>{device.serial}</Mono></dd></div>
        <div><dt>{t('Asset tag')}</dt><dd><Mono>{device.asset_tag}</Mono></dd></div>
        <div><dt>{t('Origine dati')}</dt><dd>{labelOf(SOURCES, device.source)}</dd></div>
        {device.last_seen_at && <div><dt>{t('Ultima scansione')}</dt><dd>{formatDateTime(device.last_seen_at)}</dd></div>}
        {device.sys_name && device.sys_name !== device.name && <div><dt>{t('sysName')}</dt><dd><Mono>{device.sys_name}</Mono></dd></div>}
        {customEntries.map(([key, value]) => (
          <div key={key}><dt>{key}</dt><dd>{String(value)}</dd></div>
        ))}
        {device.sys_descr && (
          <div className="facts__wide"><dt>{t('Descrizione SNMP')}</dt><dd className="hint">{device.sys_descr}</dd></div>
        )}
        {device.description && (
          <div className="facts__wide"><dt>{t('Note')}</dt><dd>{device.description}</dd></div>
        )}
      </dl>

      {stack?.items.length > 0 && (
        <StackSection device={device} members={stack.items} canEdit={canEdit} onChanged={() => { invalidate(); reloadStack() }}
          onAdd={() => setDialog({ kind: 'member' })} onEdit={(m) => setDialog({ kind: 'editMember', member: m })} />
      )}

      <section className="section">
        <header className="section__head">
          <h2>
            {t('Porte')}
            {ports && <span className="section__count">{t('{n} porte, {c} collegate', { n: ports.length, c: connected })}</span>}
          </h2>
          <div className="page-head__actions">
            {ports?.some((p) => p.endpoints > 0) && (
              <IconLink icon="search" label={t("Endpoint collegati (dov'è collegato)")} small to={`/where?device_id=${device.id}`} />
            )}
            {canEdit && <IconButton icon="plusMany" label={t('Aggiungi porte in blocco (es. Gi1/0/[1-48])')} small onClick={() => setDialog({ kind: 'bulk' })} />}
            {canEdit && <IconButton icon="plus" label={t('Aggiungi porta')} small className="btn--primary" onClick={() => setDialog({ kind: 'port' })} />}
          </div>
        </header>
        <ErrorBox error={portsError} />
        {ports && ports.length === 0 && (
          <div className="empty">
            <p>{t('Nessuna porta. Per uno switch aggiungile in blocco (il pulsante con i due quadrati qui sopra) con un intervallo come Gi1/0/[1-48].')}</p>
          </div>
        )}
        {ports && ports.length > 0 && (
          <div className="table-wrap">
            <table className="table table--dense">
              <thead>
                <tr>
                  <th>{t('Porta')}</th>
                  <th>{t('Tipo')}</th>
                  <th>{t('VLAN')}</th>
                  <th>{t('Velocità')}</th>
                  <th>{t('Collegata a')}</th>
                  <th>{t('IP')}</th>
                  <th title={t('MAC visti su questa porta nelle tabelle dello switch')}>{t('Endpoint')}</th>
                  <th className="table__actions"><span className="sr-only">{t('Azioni')}</span></th>
                </tr>
              </thead>
              <tbody>
                {ports.map((p) => (
                  <tr key={p.id} className={p.enabled ? '' : 'is-disabled'}>
                    <td>
                      {p.oper_status && (
                        <span className={`oper-dot oper-dot--${p.oper_status === 'up' ? 'up' : 'down'}`}
                          title={p.oper_status === 'up' ? t("Stato all'ultimo controllo: su") : t("Stato all'ultimo controllo: giù")} />
                      )}
                      <Mono>{p.name}</Mono>
                      {!p.enabled && <span className="tag">{t('disabilitata')}</span>}
                    </td>
                    <td>{labelOf(INTERFACE_TYPES, p.type)}</td>
                    <td><PortVlans port={p} /></td>
                    <td>{formatSpeed(p.speed_mbps)}</td>
                    <td>
                      {p.cable_id ? (
                        <>
                          <Link to={`/devices/${p.remote_device_id}`}>{p.remote_device}</Link> <Mono>{p.remote_interface}</Mono>
                          {p.cable_status === 'planned' && <span className="tag">{t('pianificato')}</span>}
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
                    <td><PortEndpoints port={p} /></td>
                    <td className="table__actions">
                      {!canEdit ? null : p.cable_id ? (
                        <IconButton icon="unlink" label={`Scollega ${p.name}`} small className="btn--ghost"
                          onClick={() => run(t('Scollegare {port} da {remote}?', { port: p.name, remote: `${p.remote_device} ${p.remote_interface}` }), () => api.del(`/cables/${p.cable_id}`))} />
                      ) : (
                        p.cableable && (
                          <IconButton icon="link" label={t("Collega {port} a un'altra porta", { port: p.name })} small className="btn--ghost"
                            onClick={() => setDialog({ kind: 'cable', portId: p.id })} />
                        )
                      )}
                      {canEdit && (
                        <>
                          <IconButton icon="edit" label={t('Modifica {name}', { name: p.name })} small className="btn--ghost"
                            onClick={() => setDialog({ kind: 'editPort', portId: p.id })} />
                          <IconButton icon="trash" label={t('Elimina {name}', { name: p.name })} small danger className="btn--ghost"
                            onClick={() => run(t('Eliminare la porta {port}?', { port: p.name }), () => api.del(`/interfaces/${p.id}`))} />
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

      <DeviceHistory deviceId={device.id} />
      <PrintFooter />

      {dialog?.kind === 'delete' && (
        <DeleteDialog resourceKey="devices" items={[device]} onClose={() => setDialog(null)}
          note={tn(ports?.length ?? 0, 'Vengono eliminate anche la sua porta e i cavi collegati.', 'Vengono eliminate anche le sue {n} porte e i cavi collegati.')}
          onDone={(result) => (result.failed.length ? window.alert(result.failed[0].error) : navigate('/devices'))} />
      )}
      {dialog?.kind === 'edit' && (
        <ResourceForm resourceKey="devices" item={device} onClose={() => setDialog(null)} onSaved={refresh} />
      )}
      {dialog?.kind === 'port' && (
        <ResourceForm resourceKey="interfaces" preset={{ device_id: device.id }} onClose={() => setDialog(null)} onSaved={refresh} />
      )}
      {dialog?.kind === 'member' && (
        <ResourceForm resourceKey="stack-members" onClose={() => setDialog(null)} onSaved={refresh}
          preset={{ device_id: device.id, number: Math.max(0, ...(stack?.items || []).map((m) => m.number)) + 1 }} />
      )}
      {dialog?.kind === 'editMember' && (
        <ResourceForm resourceKey="stack-members" item={dialog.member} onClose={() => setDialog(null)} onSaved={refresh} />
      )}
      {dialog?.kind === 'editPort' && <EditPort portId={dialog.portId} onClose={() => setDialog(null)} onSaved={refresh} />}
      {dialog?.kind === 'bulk' && <BulkPortsDialog deviceId={device.id} onClose={() => setDialog(null)} onDone={refresh} />}
      {dialog?.kind === 'cable' && (
        <CableDialog aDeviceId={device.id} aInterfaceId={dialog.portId} onClose={() => setDialog(null)} onCreated={refresh} />
      )}
    </div>
  )
}
