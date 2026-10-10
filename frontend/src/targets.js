import { LOCALE, t, tn } from './i18n'

// Indirizzi della scansione, con le regole di backend/app/discovery/targets.py: subnet, IP singolo, intervallo
// (10.0.0.1-10.0.0.20 o 10.0.0.1-20). Qui solo per le bolle e il conteggio: il controllo vero lo fa il server.
export const MAX_HOSTS = 4096

const ipv4 = (text) => {
  const parts = text.split('.')
  if (parts.length !== 4 || parts.some((p) => !/^\d{1,3}$/.test(p) || Number(p) > 255)) return null
  return parts.reduce((n, p) => n * 256 + Number(p), 0)
}
const isIpv6 = (text) => /^[0-9a-f:.]+$/i.test(text) && text.includes(':') && (text.match(/::/g) || []).length <= 1

/** {count} oppure {error}; count null = IPv6 da non contare qui */
export function parseTarget(text) {
  if (text.includes('-')) {
    const [first, rawLast] = text.split('-', 2).map((s) => s.trim())
    const start = ipv4(first)
    if (start !== null) {
      const last = /^\d+$/.test(rawLast) ? first.split('.').slice(0, 3).concat(rawLast).join('.') : rawLast
      const end = ipv4(last)
      return end !== null && end >= start ? { count: end - start + 1 } : { error: t('Intervallo non valido') }
    }
    return isIpv6(first) && isIpv6(rawLast) ? { count: null } : { error: t('Intervallo non valido') }
  }
  if (text.includes('/')) {
    const [address, bits] = text.split('/')
    const prefix = /^\d+$/.test(bits) ? Number(bits) : -1
    if (ipv4(address) !== null && prefix >= 0 && prefix <= 32) return { count: prefix < 31 ? 2 ** (32 - prefix) - 2 : 2 ** (32 - prefix) }
    if (isIpv6(address) && prefix >= 0 && prefix <= 128) return { count: 2 ** (128 - prefix) }
    return { error: t('Subnet non valida') }
  }
  if (ipv4(text) !== null || isIpv6(text)) return { count: 1 }
  return { error: t('Non è un indirizzo IP, una subnet o un intervallo') }
}

export const targetError = (text) => parseTarget(text).error

/** Riga sotto le bolle: quanti indirizzi, in rosso oltre il massimo */
export function targetsSummary(targets, max = MAX_HOSTS) {
  if (!targets.length) return null
  const total = targets.reduce((sum, target) => sum + (parseTarget(target).count ?? 0), 0)
  if (total > max) return { error: true, text: t('{n} indirizzi: il massimo è {max}', { n: total.toLocaleString(LOCALE), max }) }
  return { text: tn(total, '1 indirizzo da scansionare', '{n} indirizzi da scansionare') }
}

export const emailError = (text) => (/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(text) ? null : t('Indirizzo email non valido'))
