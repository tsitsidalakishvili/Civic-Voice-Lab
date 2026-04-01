import { requestJson } from './api'

const SUPPORTED_TRANSLATION_LANGUAGES = new Set(['en', 'ka'])
const TRANSLATION_CACHE = new Map()

export function normalizeTranslatableText(value) {
  const text = String(value ?? '').trim()
  if (!text) return ''
  return text.replace(/\s+/g, ' ')
}

function buildCacheKey(targetLanguage, sourceLanguage, text) {
  return `${sourceLanguage || 'auto'}:${targetLanguage}:${text}`
}

export async function translateBatch(texts, targetLanguage, { sourceLanguage = '' } = {}) {
  const target = String(targetLanguage || '').trim().toLowerCase()
  const source = String(sourceLanguage || '').trim().toLowerCase()
  const normalizedTexts = Array.from(
    new Set((Array.isArray(texts) ? texts : [texts]).map(normalizeTranslatableText).filter(Boolean)),
  )
  const defaultMap = normalizedTexts.reduce((acc, text) => {
    acc[text] = text
    return acc
  }, {})
  if (!normalizedTexts.length || !SUPPORTED_TRANSLATION_LANGUAGES.has(target)) {
    return defaultMap
  }

  const missingTexts = normalizedTexts.filter(
    (text) => !TRANSLATION_CACHE.has(buildCacheKey(target, source, text)),
  )

  if (missingTexts.length) {
    const response = await requestJson('/platform/translate', {
      payload: {
        texts: missingTexts,
        targetLanguage: target,
        sourceLanguage: source,
      },
    })
    const items = Array.isArray(response?.items) ? response.items : []
    items.forEach((item) => {
      const originalText = normalizeTranslatableText(item?.text)
      if (!originalText) return
      const translatedText = normalizeTranslatableText(item?.translatedText) || originalText
      TRANSLATION_CACHE.set(buildCacheKey(target, source, originalText), translatedText)
    })
  }

  return normalizedTexts.reduce((acc, text) => {
    acc[text] = TRANSLATION_CACHE.get(buildCacheKey(target, source, text)) || text
    return acc
  }, {})
}
