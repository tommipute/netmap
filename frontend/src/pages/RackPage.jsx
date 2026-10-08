import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api } from '../api'
import { useAuth } from '../auth'
import { ErrorBox, LiveStatus, Loading, PrintFooter } from '../components/Bits'
import { IconButton } from '../components/Icon'
import Modal from '../components/Modal'
import RefLabel from '../components/RefLabel'
import ResourceForm from '../components/ResourceForm'
import { invalidate, useApi, useOptions } from '../hooks'
import { t } from '../i18n'

const UNIT_PX = 26
const DRAG_THRESHOLD = 5 // px: sotto è un clic (apre il device), sopra è un trascinamento

const keyOf = (d) => `${d.id}-${d.member_id ?? 0}`
const nameOf = (d) => `${d.name}${d.member ? ` membro ${d.member}` : ''}`

/** Unità occupate dai device posizionati, escluso quello che si sta spostando: { unità: device }. */
function occupancy(view, skipKey) {
  const used = {}
  for (const d of view.devices) {
    if (keyOf(d) === skipKey) continue
    for (let u = d.position; u < d.position + d.u_height; u++) used[u] = d
  }
  return used
}

/** Le unità [pos, pos + altezza) sono libere e dentro il rack? */
function fits(view, position, height, skipKey) {
  if (position < 1 || position + height - 1 > view.u_height) return false
  const used = occupancy(view, skipKey)
  for (let u = position; u < position + height; u++) if (used[u]) return false
  return true
}

/** Salva l'unità (null = senza unità): per un membro di uno stack sul membro, altrimenti sul device. */
async function savePosition(item, position) {
  if (item.member_id) await api.patch(`/stack-members/${item.member_id}`, { rack_position: position })
  else await api.patch(`/devices/${item.id}`, { rack_position: position })
}

/**
 * Vista frontale: U numerate dal basso, device alti quanto il loro modello. Chi può modificare trascina i device
 * su un'altra unità (conta il punto dove li ha presi) e clicca un'unità libera per aggiungerne uno.
 */
function Elevation({ view, canEdit, drag, onDragStart, onEmptyUnit, bayRef }) {
  const units = Array.from({ length: view.u_height }, (_, i) => view.u_height - i)
  const used = occupancy(view, drag?.key)
  const row = (unit) => view.u_height - unit + 1 // riga della griglia (dall'alto) dell'unità
  return (
    <div className="rack" style={{ '--units': view.u_height, '--unit': `${UNIT_PX}px` }} role="img"
      aria-label={t('Rack {name}, {n} unità, {used} occupate', { name: view.name, n: view.u_height, used: view.used_units })}>
      <ol className="rack__scale" aria-hidden="true">
        {units.map((u) => <li key={u}>{u}</li>)}
      </ol>
      <div className={`rack__bay${drag ? ' rack__bay--dragging' : ''}`} ref={bayRef}>
        {units.map((u) =>
          canEdit && !used[u] ? (
            <button key={u} type="button" className="rack__slot rack__slot--free" style={{ gridRow: row(u) }}
              title={t('U{u} libera: aggiungi un device qui', { u })} aria-label={t("Aggiungi un device nell'unità {u}", { u })}
              onClick={() => onEmptyUnit(u)} />
          ) : (
            <div key={u} className="rack__slot" style={{ gridRow: row(u) }} />
          ),
        )}
        {view.devices.map((d) => {
          if (d.position > view.u_height) return null
          const bottom = row(d.position)
          const top = Math.max(1, bottom - d.u_height + 1)
          const span = bottom - top + 1
          const moving = drag?.key === keyOf(d)
          return (
            <Link key={keyOf(d)} to={`/devices/${d.id}`}
              className={`rack__device${d.conflict ? ' rack__device--conflict' : ''}${d.status !== 'active' ? ' rack__device--inactive' : ''}${canEdit ? ' rack__device--movable' : ''}${moving ? ' rack__device--moving' : ''}`}
              style={{ gridRow: `${top} / span ${span}`, '--role': d.color }}
              title={`${nameOf(d)} · U${d.position}${d.u_height > 1 ? `–${d.position + d.u_height - 1}` : ''}${d.conflict ? ` · ${t('si sovrappone a un altro device')}` : ''}${canEdit ? ` · ${t('trascina per spostarlo')}` : ''}`}
              onPointerDown={canEdit ? (e) => onDragStart(e, d) : undefined}
              draggable={false}>
              {d.reachable !== null && <span className={`live-dot live-dot--${d.reachable ? 'up' : 'down'}`} />}
              <span className="rack__name">{d.name}{d.member && <span className="rack__member"> · {d.member}</span>}</span>
              {d.face_label && span > 1 && <span className="rack__model">{d.face_label}</span>}
            </Link>
          )
        })}
        {drag?.target && (
          <div className={`rack__target${drag.target.ok ? '' : ' rack__target--bad'}`}
            style={{ gridRow: `${row(drag.target.position + drag.item.u_height - 1)} / span ${drag.item.u_height}` }}>
            U{drag.target.position}
          </div>
        )}
      </div>
    </div>
  )
}

/** Aggiunge al rack un device della stessa sede (anche spostandolo da un altro rack), all'unità scelta. */
function AddDeviceDialog({ rack, view, unit, onClose, onDone }) {
  const { data } = useApi(`/devices?site_id=${rack.site_id}&limit=1000`)
  const types = useOptions('device-types')
  const [deviceId, setDeviceId] = useState('')
  const [position, setPosition] = useState(unit ? String(unit) : '')
  const [error, setError] = useState(null)
  const [saving, setSaving] = useState(false)
  // Già al loro posto in questo rack: non si propongono
  const placed = new Set(view.devices.filter((d) => !d.member_id).map((d) => d.id))
  const candidates = (data?.items || []).filter((d) => !placed.has(d.id))
  const chosen = candidates.find((d) => d.id === Number(deviceId))
  const height = Math.max(1, types.find((dt) => dt.id === chosen?.device_type_id)?.u_height || 1)

  const submit = async (e) => {
    e.preventDefault()
    e.stopPropagation()
    if (!chosen) {
      setError(t('Scegli il device.'))
      return
    }
    const pos = position === '' ? null : Number(position)
    if (pos !== null && !fits(view, pos, height, `${chosen.id}-0`)) {
      setError(t('Le unità {units} non sono libere (o escono dal rack).', { units: `U${pos}${height > 1 ? `–${pos + height - 1}` : ''}` }))
      return
    }
    setSaving(true)
    try {
      await api.patch(`/devices/${chosen.id}`, { rack_id: rack.id, rack_position: pos })
      onDone()
    } catch (err) {
      setError(err.message)
      setSaving(false)
    }
  }

  return (
    <Modal title={t('Aggiungi un device al rack')} onClose={onClose}>
      <form className="form" onSubmit={submit} noValidate>
        <div className="form__grid">
          <div className="field field--wide">
            <label className="field__label" htmlFor="add-device">{t('Device')} <span className="field__req" aria-hidden="true">*</span></label>
            <select id="add-device" className="input" value={deviceId} onChange={(e) => setDeviceId(e.target.value)}>
              <option value="">{data ? (candidates.length ? t('Scegli…') : t('Nessun device da aggiungere in questa sede')) : t('Caricamento…')}</option>
              {candidates.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.name}{d.rack_id === rack.id ? t(' (in questo rack, senza unità)') : d.rack_id ? t(' (ora in un altro rack)') : ''}
                </option>
              ))}
            </select>
            <span className="hint">{t('Solo i device della sede del rack.')}</span>
          </div>
          <div className="field">
            <label className="field__label" htmlFor="add-unit">{t('Unità (U)')}</label>
            <input id="add-unit" type="number" className="input" min={1} max={view.u_height} value={position}
              onChange={(e) => setPosition(e.target.value)} />
            <span className="hint">
              {chosen ? `Occupa ${height} U, dalla ${position || '…'} in su.` : t("L'unità più bassa occupata.")} Vuoto: nel rack senza unità.
            </span>
          </div>
        </div>
        {error && <p className="form__error" role="alert">{error}</p>}
        <div className="modal__footer">
          <button type="button" className="btn btn--ghost" onClick={onClose}>{t('Annulla')}</button>
          <button type="submit" className="btn btn--primary" disabled={saving}>{saving ? t('Salvataggio…') : t('Aggiungi')}</button>
        </div>
      </form>
    </Modal>
  )
}

export default function RackPage() {
  const { id } = useParams()
  const navigate = useNavigate()
  const { canEdit } = useAuth()
  const { data: rack, error, reload } = useApi(`/racks/${id}`)
  const { data: view, error: viewError, reload: reloadView } = useApi(`/racks/${id}/elevation`)
  const [editing, setEditing] = useState(false)
  const [adding, setAdding] = useState(null) // null | { unit }
  const [drag, setDrag] = useState(null) // { key, item, grab, x, y, target: { position, ok } | null, overList }
  const [actionError, setActionError] = useState(null)
  const bayRef = useRef(null)
  const listRef = useRef(null)
  const viewRef = useRef(view)
  viewRef.current = view

  const refresh = () => {
    invalidate()
    reloadView()
  }

  const remove = async () => {
    if (!window.confirm(t('Eliminare il rack {name}? I device restano, senza rack.', { name: rack.name }))) return
    try {
      await api.del(`/racks/${id}`)
      invalidate()
      navigate('/racks')
    } catch (err) {
      window.alert(err.message)
    }
  }

  /** Dove cadrebbe il device con il puntatore in (x, y): unità più bassa, libera o no (null = fuori dal rack). */
  const targetAt = (x, y, item, grab, key) => {
    const bay = bayRef.current?.getBoundingClientRect()
    const v = viewRef.current
    if (!bay || x < bay.left - 40 || x > bay.right + 40 || y < bay.top - UNIT_PX || y > bay.bottom + UNIT_PX) return null
    const rowFromTop = Math.floor((y - bay.top) / UNIT_PX) // riga sotto il puntatore
    const topUnit = v.u_height - (rowFromTop - grab) // unità più alta del device
    const position = Math.min(v.u_height - item.u_height + 1, Math.max(1, topUnit - item.u_height + 1))
    return { position, ok: fits(v, position, item.u_height, key) }
  }

  // Trascinamento con il puntatore (mouse e dito): sotto la soglia è un clic e apre il device
  const startDrag = (e, item) => {
    if (e.button !== 0) return
    const key = keyOf(item)
    const box = e.currentTarget.getBoundingClientRect()
    // Riga del device dove l'ha preso (0 = la più in alto): il device si sposta restando sotto il dito
    const grab = item.position ? Math.min(item.u_height - 1, Math.max(0, Math.floor((e.clientY - box.top) / UNIT_PX))) : 0
    const start = { x: e.clientX, y: e.clientY }
    let started = false
    let current = null
    const move = (ev) => {
      if (!started && Math.hypot(ev.clientX - start.x, ev.clientY - start.y) < DRAG_THRESHOLD) return
      started = true
      ev.preventDefault()
      const list = listRef.current?.getBoundingClientRect()
      const overList = Boolean(item.position) && Boolean(list) && ev.clientX >= list.left && ev.clientX <= list.right &&
        ev.clientY >= list.top && ev.clientY <= list.bottom
      current = { key, item, grab, x: ev.clientX, y: ev.clientY, target: overList ? null : targetAt(ev.clientX, ev.clientY, item, grab, key), overList }
      setDrag(current)
    }
    const finish = () => {
      window.removeEventListener('pointermove', move)
      window.removeEventListener('pointerup', stop)
      window.removeEventListener('keydown', cancel)
      setDrag(null)
    }
    const stop = async () => {
      finish()
      if (!started) return
      // Il clic che chiude il trascinamento non apre il device
      const swallow = (ev) => {
        ev.preventDefault()
        ev.stopPropagation()
      }
      window.addEventListener('click', swallow, { capture: true, once: true })
      setTimeout(() => window.removeEventListener('click', swallow, { capture: true }), 0)
      if (!current) return
      const position = current.overList ? null : current.target?.ok ? current.target.position : undefined
      if (position === undefined || position === item.position) return
      try {
        setActionError(null)
        await savePosition(item, position)
        refresh()
      } catch (err) {
        setActionError(err.message)
      }
    }
    const cancel = (ev) => {
      if (ev.key !== 'Escape') return
      current = null
      finish()
    }
    window.addEventListener('pointermove', move)
    window.addEventListener('pointerup', stop)
    window.addEventListener('keydown', cancel)
  }

  const takeOut = async (item) => {
    const what = item.member_id ? t("Togliere l'unità al membro {n} di {name}?", { n: item.member, name: item.name }) : t('Togliere {name} dal rack?', { name: item.name })
    if (!window.confirm(what)) return
    try {
      setActionError(null)
      if (item.member_id) await savePosition(item, null)
      else await api.patch(`/devices/${item.id}`, { rack_id: null, rack_position: null })
      refresh()
    } catch (err) {
      setActionError(err.message)
    }
  }

  // Durante il trascinamento niente selezione del testo
  useEffect(() => {
    document.body.classList.toggle('is-dragging', Boolean(drag))
    return () => document.body.classList.remove('is-dragging')
  }, [drag])

  if (error) return <div className="page"><ErrorBox error={error} /></div>
  if (!rack) return <div className="page"><Loading /></div>

  const outside = view?.devices.filter((d) => d.position > view.u_height) ?? []
  const conflicts = view?.devices.filter((d) => d.conflict) ?? []
  const unplaced = [...(view?.unplaced || []), ...outside]

  return (
    <div className="page">
      <header className="page-head">
        <div>
          <p className="crumbs"><Link to="/racks">{t('Rack')}</Link></p>
          <h1>{rack.name}</h1>
          <p className="page-intro">
            <RefLabel resource="sites" id={rack.site_id} />
            {rack.location_id && <>, <RefLabel resource="locations" id={rack.location_id} /></>}
            {view && ` · ${t('{used} di {n} U occupate', { used: view.used_units, n: view.u_height })}`}
          </p>
        </div>
        <div className="page-head__actions">
          <IconButton icon="print" label={t('Stampa il rack')} onClick={() => window.print()} />
          {canEdit && view && (
            <IconButton icon="plus" label={t('Aggiungi un device al rack')} className="btn--primary" onClick={() => setAdding({ unit: null })} />
          )}
          {canEdit && <IconButton icon="edit" label={t('Modifica rack')} onClick={() => setEditing(true)} />}
          {canEdit && <IconButton icon="trash" label={t('Elimina rack')} danger className="btn--ghost" onClick={remove} />}
        </div>
      </header>

      <ErrorBox error={viewError || actionError} />
      {conflicts.length > 0 && (
        <p className="notice notice--warn">
          Alcuni device si sovrappongono o escono dal rack: {conflicts.map(nameOf).join(', ')}. Controlla unità e modello.
        </p>
      )}
      {canEdit && view && (
        <p className="hint rack-hint no-print">
          {t('Trascina un device per cambiargli unità (anche in "Nel rack senza unità" per togliergliela); clicca un\'unità libera per aggiungerne uno.')}
        </p>
      )}

      {view && (
        <div className="rack-layout">
          <Elevation view={view} canEdit={canEdit} drag={drag} bayRef={bayRef} onDragStart={startDrag}
            onEmptyUnit={(unit) => setAdding({ unit })} />
          <div className="rack-side">
            <section className={`section rack-unplaced${drag?.overList ? ' rack-unplaced--drop' : ''}`} ref={listRef}>
              <h2>{t('Nel rack senza unità')}</h2>
              {unplaced.length === 0 ? (
                <p className="muted">
                  {drag?.item.position ? t("Lascia qui il device per togliergli l'unità.") : t('Nessuno: tutti i device hanno la loro posizione.')}
                </p>
              ) : (
                <ul className="results">
                  {unplaced.map((d) => (
                    <li key={keyOf(d)} className={canEdit ? 'rack-unplaced__item' : ''}
                      onPointerDown={canEdit ? (e) => startDrag(e, d) : undefined}
                      title={canEdit ? t("Trascinalo nel rack, sull'unità giusta") : undefined}>
                      <Link to={`/devices/${d.id}`} draggable={false}>{nameOf(d)}</Link>
                      <span className="results__detail">
                        {d.position ? t("U{u}: oltre l'altezza del rack", { u: d.position }) : t("manca l'unità")}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </section>
            <section className="section">
              <h2>{t('Device')}</h2>
              {view.devices.length === 0 ? (
                <p className="muted">{t('Nessun device in questo rack.')}{canEdit ? ` ${t("Aggiungine uno con il +, o cliccando un'unità.")}` : ''}</p>
              ) : (
                <ul className="results">
                  {[...view.devices].sort((a, b) => b.position - a.position).map((d) => (
                    <li key={keyOf(d)}>
                      <span className="mono">U{d.position}</span>
                      <Link to={`/devices/${d.id}`}>{nameOf(d)}</Link>
                      <span className="results__detail">{d.face_label || d.role || ''}</span>
                      <LiveStatus device={d} />
                      {canEdit && (
                        <IconButton icon="close" label={d.member_id ? t("Togli l'unità al membro {n}", { n: d.member }) : t('Togli {name} dal rack', { name: d.name })}
                          small className="btn--ghost results__action no-print" onClick={() => takeOut(d)} />
                      )}
                    </li>
                  ))}
                </ul>
              )}
            </section>
          </div>
        </div>
      )}

      {drag && (
        <div className="rack-ghost" style={{ left: drag.x + 14, top: drag.y + 10 }} aria-hidden="true">
          {nameOf(drag.item)}
          <span className="muted">
            {drag.overList ? t(' → senza unità') : drag.target ? (drag.target.ok ? ` → U${drag.target.position}` : t(' → occupato')) : ''}
          </span>
        </div>
      )}

      <PrintFooter />

      {adding && view && (
        <AddDeviceDialog rack={rack} view={view} unit={adding.unit} onClose={() => setAdding(null)}
          onDone={() => { setAdding(null); refresh() }} />
      )}
      {editing && (
        <ResourceForm resourceKey="racks" item={rack} onClose={() => setEditing(false)}
          onSaved={() => { setEditing(false); reload(); reloadView() }} />
      )}
    </div>
  )
}
