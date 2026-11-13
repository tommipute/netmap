import { useRef } from 'react'
import { api } from '../api'
import { useAuth } from '../auth'
import { invalidate } from '../hooks'
import { t, tn } from '../i18n'
import { IconButton } from './Icon'

/** Export e import del file delle regole SNMP (JSON), per passarle tra installazioni o allegarle a una segnalazione. */
export default function SnmpRuleFile({ onImported }) {
  const { isAdmin } = useAuth()
  const input = useRef(null)
  if (!isAdmin) return null

  const download = async () => {
    try {
      const data = await api.get('/snmp-rules/export')
      const a = document.createElement('a')
      a.href = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2) + '\n'], { type: 'application/json' }))
      a.download = 'netmap-regole-snmp.json'
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(a.href)
    } catch (err) {
      window.alert(err.message)
    }
  }

  const upload = async (file) => {
    if (!file) return
    try {
      let data
      try {
        data = JSON.parse(await file.text())
      } catch {
        throw new Error(t('Il file non è un JSON valido.'))
      }
      const result = await api.post('/snmp-rules/import', data)
      invalidate()
      onImported?.()
      window.alert(t('Regole importate: {created}, {updated}.', {
        created: tn(result.created, '1 nuova', '{n} nuove'),
        updated: tn(result.updated, '1 aggiornata', '{n} aggiornate'),
      }))
    } catch (err) {
      window.alert(err.message)
    } finally {
      input.current.value = ''
    }
  }

  return (
    <>
      <IconButton icon="download" label={t('Esporta tutte le regole in un file JSON')} onClick={download}>
        <span className="btn__tag">{t('JSON')}</span>
      </IconButton>
      <IconButton icon="upload" label={t('Importa regole da un file JSON: quelle con lo stesso nome si aggiornano')} onClick={() => input.current.click()} />
      <input ref={input} type="file" accept=".json,application/json" hidden onChange={(e) => upload(e.target.files[0])} />
    </>
  )
}
