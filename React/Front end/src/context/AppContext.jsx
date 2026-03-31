import { createContext, useContext, useEffect, useMemo, useState } from 'react'
import { LANGUAGES, createTranslator } from '../i18n'
import { getInitialLanguage } from '../utils/language'

const AppContext = createContext(null)

export function AppProvider({ children }) {
  const [language, setLanguage] = useState(getInitialLanguage)

  useEffect(() => {
    localStorage.setItem('fs_lang', language)
  }, [language])

  useEffect(() => {
    document.documentElement.lang = language
  }, [language])

  const t = useMemo(() => createTranslator(language), [language])

  const value = useMemo(
    () => ({ language, setLanguage, t, languages: LANGUAGES }),
    [language, t],
  )

  return <AppContext.Provider value={value}>{children}</AppContext.Provider>
}

export const useApp = () => {
  const ctx = useContext(AppContext)
  if (!ctx) throw new Error('useApp must be used within AppProvider')
  return ctx
}
