import { LANGUAGES } from '../i18n'

export const normalizeLanguage = (value) => {
  if (!value) return ''
  const normalized = String(value).trim().toLowerCase()
  if (!normalized) return ''
  const exact = LANGUAGES.find((lang) => lang.id.toLowerCase() === normalized)
  if (exact) return exact.id
  const prefix = normalized.split('-')[0]
  const match = LANGUAGES.find((lang) => lang.id.toLowerCase() === prefix)
  return match ? match.id : ''
}

export const detectBrowserLanguage = () => {
  if (typeof navigator === 'undefined') return ''
  const candidates = Array.isArray(navigator.languages)
    ? navigator.languages
    : [navigator.language]
  for (const candidate of candidates) {
    const normalized = normalizeLanguage(candidate)
    if (normalized) return normalized
  }
  return ''
}

export const getInitialLanguage = () => {
  if (typeof window === 'undefined') return 'en'
  const params = new URLSearchParams(window.location.search)
  const fromUrl = normalizeLanguage(
    params.get('lang') || params.get('language') || params.get('ui_lang'),
  )
  if (fromUrl) return fromUrl
  const stored = normalizeLanguage(localStorage.getItem('fs_lang'))
  if (stored) return stored
  return detectBrowserLanguage() || 'en'
}
