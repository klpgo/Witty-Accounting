import {
  type ReactNode,
  useEffect,
  useMemo,
} from 'react'

import { useAuth } from '../auth/useAuth'
import { useAppSettings } from '../settings/useAppSettings'
import { I18nContext } from './i18nContext'
import {
  type Language,
  normalizeLanguage,
  translate,
} from './translate'

/*
 * Sprache der Oberfläche: persönliche Wahl des angemeldeten Benutzers,
 * sonst die Standardsprache des Mandanten (auch vor der Anmeldung).
 */
export function I18nProvider({ children }: { children: ReactNode }) {
  const { defaultLanguage } = useAppSettings()
  const { user } = useAuth()

  const language: Language =
    normalizeLanguage(user?.language) ??
    normalizeLanguage(defaultLanguage) ??
    'de'

  useEffect(() => {
    document.documentElement.lang = language
  }, [language])

  const value = useMemo(
    () => ({
      language,
      t: (key: Parameters<typeof translate>[1], params?: Parameters<typeof translate>[2]) =>
        translate(language, key, params),
    }),
    [language],
  )

  return (
    <I18nContext.Provider value={value}>
      {children}
    </I18nContext.Provider>
  )
}
