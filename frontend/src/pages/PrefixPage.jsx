import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api } from '../api'
import { useAuth } from '../auth'
import { Badge, ErrorBox, Loading, Mono } from '../components/Bits'
import { IconButton } from '../components/Icon'
import RefLabel from '../components/RefLabel'
import ResourceForm from '../components/ResourceForm'
import { invalidate, useApi } from '../hooks'
import { IP_STATUS, IPAM_STATUS } from '../options'
import { LOCALE, t } from '../i18n'

export default function PrefixPage() {
  const { canEdit } = useAuth()
  const { id } = useParams()
  const navigate = useNavigate()
  const { data: prefix, error, reload } = useApi(`/prefixes/${id}`)
  const usage = useApi(`/prefixes/${id}/utilization`)
  const ips = useApi(`/prefixes/${id}/ip-addresses`)
  const free = useApi(`/prefixes/${id}/available-ips?limit=12`)
  const [dialog, setDialog] = useState(null)

  const refresh = () => {
    setDialog(null)
    reload()
    usage.reload()
    ips.reload()
    free.reload()
  }

  const remove = async () => {
    if (!window.confirm(t('Eliminare la subnet {prefix}? Gli indirizzi IP registrati restano.', { prefix: prefix.prefix }))) return
    try {
      await api.del(`/prefixes/${id}`)
      invalidate()
      navigate('/prefixes')
    } catch (err) {
      window.alert(err.message)
    }
  }

  if (error) return <div className="page"><ErrorBox error={error} /></div>
  if (!prefix) return <div className="page"><Loading /></div>

  const u = usage.data
  const level = u ? (u.percent >= 90 ? 'danger' : u.percent >= 70 ? 'warn' : 'ok') : 'ok'

  return (
    <div className="page">
      <header className="page-head">
        <div>
          <p className="crumbs"><Link to="/prefixes">{t('Subnet')}</Link></p>
          <h1 className="device-title">
            <span className="mono">{prefix.prefix}</span>
            <Badge value={prefix.status} options={IPAM_STATUS} />
          </h1>
          {prefix.description && <p className="page-intro">{prefix.description}</p>}
        </div>
        <div className="page-head__actions">
          {canEdit && <IconButton icon="edit" label={t('Modifica subnet')} onClick={() => setDialog({ kind: 'edit' })} />}
          {canEdit && <IconButton icon="trash" label={t('Elimina subnet')} danger className="btn--ghost" onClick={remove} />}
        </div>
      </header>

      <dl className="facts">
        <div><dt>{t('Sede')}</dt><dd><RefLabel resource="sites" id={prefix.site_id} /></dd></div>
        <div><dt>{t('VLAN')}</dt><dd><RefLabel resource="vlans" id={prefix.vlan_id} /></dd></div>
        <div><dt>{t('VRF')}</dt><dd><RefLabel resource="vrfs" id={prefix.vrf_id} empty={t('Globale')} /></dd></div>
      </dl>

      {u && (
        <section className="section">
          <div className={`meter meter--${level}`} role="meter" aria-valuemin={0} aria-valuemax={100} aria-valuenow={u.percent} aria-label={t('Utilizzo della subnet')}>
            <div className="meter__fill" style={{ width: `${Math.max(u.percent, u.used ? 1 : 0)}%` }} />
          </div>
          <p className="meter__text">
            {t('{used} indirizzi registrati su {total} utilizzabili ({percent}%)', { used: u.used, total: u.total.toLocaleString(LOCALE), percent: u.percent.toLocaleString(LOCALE) })}
          </p>
        </section>
      )}

      <section className="section">
        <header className="section__head">
          <h2>{t('Primi indirizzi liberi')}</h2>
        </header>
        {free.data && free.data.length === 0 && <p className="muted">{t('La subnet è piena.')}</p>}
        {free.data && free.data.length > 0 && (
          <div className="chips">
            {free.data.map((address) => (
              <button key={address} type="button" className="chip chip--action" title={t('Registra questo indirizzo')}
                disabled={!canEdit} onClick={() => setDialog({ kind: 'ip', address })}>
                <span className="mono">{address.split('/')[0]}</span>
              </button>
            ))}
          </div>
        )}
        <p className="hint">{t('Clicca un indirizzo per registrarlo e assegnarlo a una porta.')}</p>
      </section>

      <section className="section">
        <header className="section__head">
          <h2>
            {t('Indirizzi registrati')}
            {ips.data && <span className="section__count">{ips.data.length}</span>}
          </h2>
        </header>
        <ErrorBox error={ips.error} />
        {ips.data && ips.data.length === 0 && <p className="muted">{t('Nessun indirizzo registrato in questa subnet.')}</p>}
        {ips.data && ips.data.length > 0 && (
          <div className="table-wrap">
            <table className="table table--dense">
              <thead>
                <tr>
                  <th>{t('Indirizzo')}</th>
                  <th>{t('Assegnato a')}</th>
                  <th>{t('Nome DNS')}</th>
                  <th>{t('Stato')}</th>
                  <th className="table__actions"><span className="sr-only">{t('Azioni')}</span></th>
                </tr>
              </thead>
              <tbody>
                {ips.data.map((ip) => (
                  <tr key={ip.id}>
                    <td><span className="mono strong">{ip.address}</span></td>
                    <td>
                      {ip.device_id ? (
                        <>
                          <Link to={`/devices/${ip.device_id}`}>{ip.device_name}</Link> <Mono>{ip.interface_name}</Mono>
                          {ip.is_primary && <span className="tag">{t('management')}</span>}
                        </>
                      ) : (
                        <span className="muted">{t('Non assegnato')}</span>
                      )}
                    </td>
                    <td><Mono>{ip.dns_name}</Mono></td>
                    <td><Badge value={ip.status} options={IP_STATUS} /></td>
                    <td className="table__actions">
                      {canEdit && (
                        <IconButton icon="edit" label={t('Modifica {name}', { name: ip.address })} small className="btn--ghost"
                          onClick={() => setDialog({ kind: 'editIp', item: ip })} />
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {dialog?.kind === 'edit' && <ResourceForm resourceKey="prefixes" item={prefix} onClose={() => setDialog(null)} onSaved={refresh} />}
      {dialog?.kind === 'ip' && (
        <ResourceForm resourceKey="ip-addresses" preset={{ address: dialog.address, vrf_id: prefix.vrf_id }}
          onClose={() => setDialog(null)} onSaved={refresh} />
      )}
      {dialog?.kind === 'editIp' && <ResourceForm resourceKey="ip-addresses" item={dialog.item} onClose={() => setDialog(null)} onSaved={refresh} />}
    </div>
  )
}
