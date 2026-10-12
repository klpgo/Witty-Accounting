import { createContext } from 'react'

export type AppSettingsStatus =
  | 'loading'
  | 'ready'

export interface AppSettingsContextValue {
  appName: string
  tenantName: string
  // Standardsprache des Mandanten ('de' | 'en')
  defaultLanguage: string
  // Umsatzsteuer ausweisen (aus bei Kleinunternehmern)
  vatEnabled: boolean
  status: AppSettingsStatus
  refreshSettings: () => Promise<void>
}

export const AppSettingsContext =
  createContext<AppSettingsContextValue | null>(
    null,
  )
