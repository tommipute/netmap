import { t } from '../i18n'

// Colori dei cavi come nella realtà: patch in rame blu, fibra OM3/OM4 acqua, monomodale gialla, DAC scuro.
export const CABLE_STYLES = {
  cat5e: { color: '#7C97B8', label: 'Cat5e' },
  cat6: { color: '#4A7DBA', label: 'Cat6' },
  cat6a: { color: '#3567A3', label: 'Cat6a' },
  fiber_mm: { color: '#00A3AD', label: t('Fibra multimodale') },
  fiber_sm: { color: '#D9A400', label: t('Fibra monomodale') },
  dac: { color: '#6B7480', label: 'DAC' },
}
export const DEFAULT_CABLE = { color: '#8A94A3', label: t('Tipo non indicato') }

export function cableStyle(type) {
  return CABLE_STYLES[type] || DEFAULT_CABLE
}
