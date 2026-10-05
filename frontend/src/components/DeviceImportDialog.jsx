import { useState, useRef } from 'react'
import { api } from '../api'
import { ErrorBox, Loading } from './Bits'
import Modal from './Modal'

export default function DeviceImportDialog({ onClose, onImported }) {
  const [csvText, setCsvText] = useState('')
  const [fileName, setFileName] = useState('')
  const [updateExisting, setUpdateExisting] = useState(true)
  const [dryRun, setDryRun] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [result, setResult] = useState(null)
  const fileInputRef = useRef(null)

  const handleFileChange = (e) => {
    const file = e.target.files?.[0]
    if (!file) return
    setFileName(file.name)
    setError(null)
    setResult(null)
    const reader = new FileReader()
    reader.onload = (event) => {
      setCsvText(event.target.result || '')
    }
    reader.onerror = () => {
      setError('Errore durante la lettura del file.')
    }
    reader.readAsText(file, 'utf-8')
  }

  const handleDownloadTemplate = () => {
    window.location.href = '/api/devices/import/template'
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (!csvText.trim()) {
      setError('Seleziona un file CSV o incolla i dati da importare.')
      return
    }
    setLoading(true)
    setError(null)
    setResult(null)
    try {
      const res = await api.post('/devices/import', {
        csv_data: csvText,
        update_existing: updateExisting,
        dry_run: dryRun,
      })
      setResult(res)
      if (!dryRun && (res.created_count > 0 || res.updated_count > 0)) {
        onImported?.()
      }
    } catch (err) {
      setError(err.message || 'Errore durante l\'importazione.')
    } finally {
      setLoading(false)
    }
  }

  const hasData = Boolean(csvText.trim())

  return (
    <Modal title="Importa device" wide onClose={onClose}>
      <form onSubmit={handleSubmit} className="form">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '14px', flexWrap: 'wrap', gap: '8px' }}>
          <p className="page-intro" style={{ margin: 0 }}>
            Importa o aggiorna device con sedi, posizioni, rack, modelli, ruoli e IP di management da un file CSV.
          </p>
          <button
            type="button"
            className="btn btn--sm"
            onClick={handleDownloadTemplate}
            title="Scarica un file CSV di esempio con le colonne corrette"
          >
            Scarica modello CSV
          </button>
        </div>

        <ErrorBox error={error} />

        {/* Selezione file */}
        <div className="field" style={{ marginBottom: '14px' }}>
          <label className="field__label">Seleziona file CSV</label>
          <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
            <input
              ref={fileInputRef}
              type="file"
              accept=".csv,.txt"
              onChange={handleFileChange}
              style={{ display: 'none' }}
            />
            <button
              type="button"
              className="btn btn--sm"
              onClick={() => fileInputRef.current?.click()}
            >
              {fileName ? 'Scegli un altro file...' : 'Sfoglia file...'}
            </button>
            {fileName && <span className="mono" style={{ fontSize: '13px' }}>{fileName}</span>}
          </div>
        </div>

        {/* Area di testo per incollare o visualizzare il CSV */}
        <div className="field" style={{ marginBottom: '14px' }}>
          <label className="field__label">
            Anteprima o inserimento manuale CSV
            <span className="hint" style={{ marginLeft: '8px' }}>
              (separatore virgola o punto e virgola, intestazioni in italiano o inglese)
            </span>
          </label>
          <textarea
            className="input mono"
            style={{ width: '100%', minHeight: '120px', fontSize: '12px' }}
            placeholder={`name;status;site;location;rack;rack_position;manufacturer;model;role;primary_ip;serial;asset_tag;description\nsw-01;active;Sede principale;CED;R01;42;Cisco;Catalyst 9300-48P;Core;10.10.99.1/24;FOC1234;AST-001;Switch principale`}
            value={csvText}
            onChange={(e) => {
              setCsvText(e.target.value)
              setResult(null)
            }}
          />
        </div>

        {/* Opzioni */}
        <div style={{ display: 'flex', gap: '20px', marginBottom: '16px', flexWrap: 'wrap' }}>
          <label className="check check--inline">
            <input
              type="checkbox"
              checked={updateExisting}
              onChange={(e) => setUpdateExisting(e.target.checked)}
            />
            <span>Aggiorna i device se già esistenti (stessa sede e nome)</span>
          </label>
          <label className="check check--inline">
            <input
              type="checkbox"
              checked={dryRun}
              onChange={(e) => setDryRun(e.target.checked)}
            />
            <span>Simulazione (Dry-run, non scrive nel database)</span>
          </label>
        </div>

        {/* Risultato dell'importazione */}
        {result && (
          <div
            style={{
              padding: '14px 16px',
              borderRadius: '6px',
              marginBottom: '16px',
              border: '1px solid var(--line)',
              background: result.errors.length === 0 ? 'var(--surface-2)' : 'var(--surface)',
            }}
          >
            <div style={{ display: 'flex', gap: '14px', alignItems: 'center', marginBottom: result.errors.length ? '10px' : 0 }}>
              <strong>{result.dry_run ? 'Risultato simulazione:' : 'Importazione completata:'}</strong>
              <span className="badge badge--ok">{result.created_count} creati</span>
              <span className="badge badge--info">{result.updated_count} aggiornati</span>
              {result.skipped_count > 0 && <span className="badge badge--muted">{result.skipped_count} ignorati</span>}
              {result.errors.length > 0 && <span className="badge badge--danger">{result.errors.length} errori</span>}
            </div>

            {result.created_devices.length > 0 && (
              <p className="hint" style={{ marginTop: '6px' }}>
                Creati: <span className="mono">{result.created_devices.join(', ')}</span>
              </p>
            )}
            {result.updated_devices.length > 0 && (
              <p className="hint" style={{ marginTop: '4px' }}>
                Aggiornati: <span className="mono">{result.updated_devices.join(', ')}</span>
              </p>
            )}

            {result.errors.length > 0 && (
              <div style={{ marginTop: '12px' }}>
                <strong style={{ color: 'var(--danger)', fontSize: '13px' }}>Errori riscontrati:</strong>
                <ul style={{ margin: '6px 0 0 18px', padding: 0, fontSize: '13px', color: 'var(--danger)' }}>
                  {result.errors.map((err, i) => (
                    <li key={i}>
                      Riga {err.row}{err.device ? ` (${err.device})` : ''}: {err.error}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}

        {loading && <Loading />}

        <footer className="modal__footer">
          <button type="button" className="btn btn--ghost" onClick={onClose} disabled={loading}>
            {result && !result.dry_run && (result.created_count > 0 || result.updated_count > 0) ? 'Fatto' : 'Annulla'}
          </button>
          <button
            type="submit"
            className="btn btn--primary"
            disabled={!hasData || loading}
          >
            {loading ? 'Elaborazione in corso...' : dryRun ? 'Esegui simulazione' : 'Avvia importazione'}
          </button>
        </footer>
      </form>
    </Modal>
  )
}
