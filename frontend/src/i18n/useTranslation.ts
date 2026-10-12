import { useContext } from 'react'

import { I18nContext, type I18nContextValue } from './i18nContext'

export function useTranslation(): I18nContextValue {
  const context = useContext(I18nContext)

  if (context === undefined) {
    throw new Error('useTranslation muss innerhalb von I18nProvider verwendet werden.')
  }

  return context
}
