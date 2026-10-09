import { useState, useRef } from 'react'
import { api } from '../api'
import { ErrorBox, Loading } from './Bits'
import Modal from './Modal'
import { t, tn, tServer } from '../i18n'

export default function DeviceImportDialog({ onClose, onImported }) {
  const [csvText, setCsvText] = useState('')
  const [fileName, setFileName] = useState('')
  const [sheet, setSheet] = useState(null) // foglio letto da un file Excel
  const [updateExisting, setUpdateExisting] = useState(true)
  const [dryRun, setDryRun] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [result, setResult] = useState(null)
  const fileInputRef = useRef(null)

  const handleFileChange = (e) => {
    const file = e.target.files?.[0]
    if (!file) return
    e.target.value = '' // lo stesso file si può scegliere di nuovo (es. dopo averlo corretto in Excel)
    setFileName(file.name)
    setError(null)
    setResult(null)
    setSheet(null)
    if (/\.xls[xm]?$/i.test(file.name)) {
      // Excel: lo converte il server, poi si vede e si importa come un CSV
      setLoading(true)
      api.post('/devices/import/xlsx', file)
        .then((res) => {
          setCsvText(res.csv_data)
          setSheet(res)
        })
        .catch((err) => {
          setCsvText('')
          setError(err.message)
        })
        .finally(() => setLoading(false))
      return
    }
    const reader = new FileReader()
    reader.onload = (event) => {
      setCsvText(event.target.result || '')
    }
    reader.onerror = () => {
      setError(t('Errore durante la lettura del file.'))
    }
    reader.readAsText(file, 'utf-8')
  }

  const handleDownloadTemplate = () => {
    window.location.href = '/api/devices/import/template'
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (!csvText.trim()) {
      setError(t('Seleziona un file CSV o incolla i dati da importare.'))
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
      setError(err.message || t('Errore durante l\'importazione.'))
    } finally {
      setLoading(false)
    }
  }

  const hasData = Boolean(csvText.trim())

  return (
    <Modal title={t('Importa device')} wide onClose={onClose}>
      <form onSubmit={handleSubmit} className="form">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '14px', flexWrap: 'wrap', gap: '8px' }}>
          <p className="page-intro" style={{ margin: 0 }}>
            {t('Importa o aggiorna device con sedi, posizioni, rack, modelli, ruoli e IP di management da un file CSV o Excel (.xlsx).')}
          </p>
          <button
            type="button"
            className="btn btn--sm"
            onClick={handleDownloadTemplate}
            title={t('Scarica un file CSV di esempio con le colonne corrette')}
          >
            {t('Scarica modello CSV')}
          </button>
        </div>

        <ErrorBox error={error} />

        {/* Selezione file */}
        <div className="field" style={{ marginBottom: '14px' }}>
          <label className="field__label">{t('Seleziona file CSV o Excel')}</label>
          <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
            <input
              ref={fileInputRef}
              type="file"
              accept=".csv,.txt,.xlsx,.xlsm"
              onChange={handleFileChange}
              style={{ display: 'none' }}
            />
            <button
              type="button"
              className="btn btn--sm"
              onClick={() => fileInputRef.current?.click()}
            >
              {fileName ? t('Scegli un altro file...') : t('Sfoglia file...')}
            </button>
            {fileName && <span className="mono" style={{ fontSize: '13px' }}>{fileName}</span>}
          </div>
          {sheet && (
            <span className="hint">
              {tn(sheet.rows, 'Foglio "{sheet}": 1 riga, convertita qui sotto.', 'Foglio "{sheet}": {n} righe, convertite qui sotto.', { sheet: sheet.sheet })}
            </span>
          )}
        </div>

        {/* Area di testo per incollare o visualizzare il CSV */}
        <div className="field" style={{ marginBottom: '14px' }}>
          <label className="field__label">
            {t('Anteprima o inserimento manuale CSV')}
            <span className="hint" style={{ marginLeft: '8px' }}>
              {t('(separatore virgola o punto e virgola, intestazioni in italiano o inglese)')}
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
            <span>{t('Aggiorna i device se già esistenti (stessa sede e nome)')}</span>
          </label>
          <label className="check check--inline">
            <input
              type="checkbox"
              checked={dryRun}
              onChange={(e) => setDryRun(e.target.checked)}
            />
            <span>{t('Simulazione (Dry-run, non scrive nel database)')}</span>
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
              <strong>{result.dry_run ? t('Risultato simulazione:') : t('Importazione completata:')}</strong>
              <span className="badge badge--ok">{tn(result.created_count, '1 creato', '{n} creati')}</span>
              <span className="badge badge--info">{tn(result.updated_count, '1 aggiornato', '{n} aggiornati')}</span>
              {result.skipped_count > 0 && <span className="badge badge--muted">{tn(result.skipped_count, '1 ignorato', '{n} ignorati')}</span>}
              {result.errors.length > 0 && <span className="badge badge--danger">{tn(result.errors.length, '1 errore', '{n} errori')}</span>}
            </div>

            {result.created_devices.length > 0 && (
              <p className="hint" style={{ marginTop: '6px' }}>
                {t('Creati:')} <span className="mono">{result.created_devices.join(', ')}</span>
              </p>
            )}
            {result.updated_devices.length > 0 && (
              <p className="hint" style={{ marginTop: '4px' }}>
                {t('Aggiornati:')} <span className="mono">{result.updated_devices.join(', ')}</span>
              </p>
            )}

            {result.errors.length > 0 && (
              <div style={{ marginTop: '12px' }}>
                <strong style={{ color: 'var(--danger)', fontSize: '13px' }}>{t('Errori riscontrati:')}</strong>
                <ul style={{ margin: '6px 0 0 18px', padding: 0, fontSize: '13px', color: 'var(--danger)' }}>
                  {result.errors.map((err, i) => (
                    <li key={i}>
                      {t('Riga {row}', { row: err.row })}{err.device ? ` (${err.device})` : ''}: {tServer(err.error)}
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
            {result && !result.dry_run && (result.created_count > 0 || result.updated_count > 0) ? t('Fatto') : t('Annulla')}
          </button>
          <button
            type="submit"
            className="btn btn--primary"
            disabled={!hasData || loading}
          >
            {loading ? t('Elaborazione in corso...') : dryRun ? t('Esegui simulazione') : t('Avvia importazione')}
          </button>
        </footer>
      </form>
    </Modal>
  )
}
