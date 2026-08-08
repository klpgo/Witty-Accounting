import { useContext } from 'react'

import { AppSettingsContext } from './appSettingsContext'

export function useAppSettings() {
  const context = useContext(
    AppSettingsContext,
  )

  if (context === null) {
    throw new Error(
      'useAppSettings muss innerhalb des '
      + 'AppSettingsProvider verwendet werden.',
    )
  }

  return context
}
