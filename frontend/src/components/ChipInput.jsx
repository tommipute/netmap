import { useState } from 'react'
import { t } from '../i18n'

const SEPARATORS = /[\s,;]+/

/**
 * Elenco di valori a "bolle": si scrive e Invio, virgola, spazio o punto e virgola fanno la bolla; un elenco
 * incollato diventa tante bolle; la × (o Backspace a casella vuota) la toglie. validate(testo) -> motivo se non va
 * bene (bolla rossa, motivo nel tooltip); summary(valori) -> riga sotto le bolle (es. quanti indirizzi).
 */
export default function ChipInput({ id, value, onChange, placeholder, disabled, validate, summary, label }) {
  const [text, setText] = useState('')
  const chips = value || []

  const add = (raw) => {
    const added = raw.split(SEPARATORS).map((part) => part.trim()).filter((part) => part && !chips.includes(part))
    if (added.length) onChange([...chips, ...new Set(added)])
    setText('')
  }
  const remove = (index) => onChange(chips.filter((_, i) => i !== index))

  const onKeyDown = (e) => {
    if (['Enter', ',', ';', ' '].includes(e.key) || (e.key === 'Tab' && text.trim())) {
      if (e.key !== 'Tab' || text.trim()) e.preventDefault() // Invio non deve inviare il modulo
      if (text.trim()) add(text)
    } else if (e.key === 'Backspace' && !text && chips.length) {
      remove(chips.length - 1)
    }
  }
  const onPaste = (e) => {
    const pasted = e.clipboardData.getData('text')
    if (!SEPARATORS.test(pasted.trim())) return // un valore solo: lo incolla nella casella come sempre
    e.preventDefault()
    add(`${text} ${pasted}`) // quello già scritto resta una bolla a sé
  }

  const errors = chips.map((chip) => validate?.(chip) || null)
  const note = summary?.(chips.filter((_, i) => !errors[i]))
  return (
    <>
      <div className={`chip-input${disabled ? ' is-disabled' : ''}`} onClick={() => document.getElementById(id)?.focus()}>
        {chips.map((chip, i) => (
          <span key={chip} className={`chip chip--value${errors[i] ? ' chip--invalid' : ''}`} title={errors[i] || undefined}>
            <span className="mono">{chip}</span>
            {!disabled && (
              <button type="button" className="chip__remove" onClick={() => remove(i)} aria-label={t('Togli {value}', { value: chip })}>
                ×
              </button>
            )}
          </span>
        ))}
        <input id={id} className="chip-input__text mono" value={text} disabled={disabled} aria-label={label}
          placeholder={chips.length ? '' : placeholder} onChange={(e) => setText(e.target.value)}
          onKeyDown={onKeyDown} onPaste={onPaste} onBlur={() => text.trim() && add(text)} />
      </div>
      {errors.some(Boolean) && (
        <span className="hint hint--error">{t('Le bolle rosse non sono valide: passaci sopra per vedere perché.')}</span>
      )}
      {note && <span className={`hint${note.error ? ' hint--error' : ''}`}>{note.text}</span>}
    </>
  )
}
