import { useState } from 'react'
import { IconButton } from './Icon'
import { t } from '../i18n'

/** Chiave casuale di 32 byte in base64url (43 caratteri), dal generatore crittografico del browser. */
export function randomKey() {
  const bytes = crypto.getRandomValues(new Uint8Array(32))
  return btoa(String.fromCharCode(...bytes)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')
}

/** Copia negli appunti: navigator.clipboard c'è solo in HTTPS o su localhost, altrimenti il vecchio execCommand. */
export async function copyText(text) {
  if (navigator.clipboard && window.isSecureContext) {
    await navigator.clipboard.writeText(text)
    return
  }
  const area = document.createElement('textarea')
  area.value = text
  area.setAttribute('readonly', '')
  area.style.position = 'fixed'
  area.style.opacity = '0'
  document.body.appendChild(area)
  area.select()
  const ok = document.execCommand('copy')
  area.remove()
  if (!ok) throw new Error('copy')
}

/** Campo segreto con "Genera una chiave": la chiave generata resta visibile, per copiarla nel programma che riceve. */
export default function SecretInput({ id, value, onChange, placeholder, disabled }) {
  const [shown, setShown] = useState(false)
  const [copied, setCopied] = useState(false)
  const generate = () => {
    onChange(randomKey())
    setShown(true)
    setCopied(false)
  }
  const copy = async () => {
    try {
      await copyText(value)
      setCopied(true)
    } catch {
      setCopied(false)
    }
  }
  return (
    <div className="secret-input">
      <input id={id} type={shown ? 'text' : 'password'} className={`input${shown ? ' mono' : ''}`} value={value}
        autoComplete="new-password" disabled={disabled} placeholder={placeholder}
        onChange={(e) => { onChange(e.target.value); setCopied(false) }} />
      <IconButton icon="key" label={t('Genera una chiave')} disabled={disabled} onClick={generate} />
      {shown && value && <IconButton icon={copied ? 'check' : 'copy'} label={copied ? t('Copiato') : t('Copia la chiave')} onClick={copy} />}
    </div>
  )
}
