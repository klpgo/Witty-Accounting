import { createContext } from 'react'

export type AppSettingsStatus =
  | 'loading'
  | 'ready'

export interface AppSettingsContextValue {
  appName: string
  status: AppSettingsStatus
  refreshSettings: () => Promise<void>
}

export const AppSettingsContext =
  createContext<AppSettingsContextValue | null>(
    null,
  )
