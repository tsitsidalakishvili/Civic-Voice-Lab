import { useEffect, useMemo, useState } from 'react'
import { normalizeTranslatableText, translateBatch } from '../services/translation'

export function useTextTranslations(texts, language, { enabled = true, sourceLanguage = '' } = {}) {
  const normalizedTexts = useMemo(
    () =>
      Array.from(
        new Set((Array.isArray(texts) ? texts : [texts]).map(normalizeTranslatableText).filter(Boolean)),
      ),
    [texts],
  )
  const textSignature = useMemo(() => normalizedTexts.join('\u0001'), [normalizedTexts])
  const [translationMap, setTranslationMap] = useState({})

  useEffect(() => {
    let cancelled = false
    const fallbackMap = normalizedTexts.reduce((acc, text) => {
      acc[text] = text
      return acc
    }, {})

    if (!enabled || !normalizedTexts.length) {
      setTranslationMap(fallbackMap)
      return () => {
        cancelled = true
      }
    }

    translateBatch(normalizedTexts, language, { sourceLanguage })
      .then((nextMap) => {
        if (!cancelled) setTranslationMap(nextMap)
      })
      .catch(() => {
        if (!cancelled) setTranslationMap(fallbackMap)
      })

    return () => {
      cancelled = true
    }
  }, [enabled, language, sourceLanguage, textSignature])

  const translateText = (value, fallback = '') => {
    const normalized = normalizeTranslatableText(value)
    if (!normalized) return fallback || String(value ?? '')
    return translationMap[normalized] || normalized
  }

  return { translationMap, translateText }
}
