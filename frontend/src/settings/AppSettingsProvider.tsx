import {
  type ReactNode,
  useCallback,
  useEffect,
  useMemo,
  useState,
} from 'react'

import { getPublicSettings } from '../api/settings'
import {
  AppSettingsContext,
  type AppSettingsStatus,
} from './appSettingsContext'

const DEFAULT_APP_NAME = 'Witty-Accounting'

interface AppSettingsProviderProps {
  children: ReactNode
}

export function AppSettingsProvider({
  children,
}: AppSettingsProviderProps) {
  const [appName, setAppName] = useState(
    DEFAULT_APP_NAME,
  )
  const [tenantName, setTenantName] = useState(
    DEFAULT_APP_NAME,
  )

  const [status, setStatus] =
    useState<AppSettingsStatus>('loading')

  const refreshSettings =
    useCallback(async (): Promise<void> => {
      try {
        const publicSettings =
          await getPublicSettings()

        const normalizedName =
          publicSettings.app_name.trim()
        const normalizedTenantName =
          publicSettings.tenant_name.trim()

        setAppName(
          normalizedName || DEFAULT_APP_NAME,
        )
        setTenantName(
          normalizedTenantName || DEFAULT_APP_NAME,
        )
      } catch {
        setAppName(DEFAULT_APP_NAME)
        setTenantName(DEFAULT_APP_NAME)
      } finally {
        setStatus('ready')
      }
    }, [])

  useEffect(() => {
    void refreshSettings()
  }, [refreshSettings])

  useEffect(() => {
    document.title = appName
  }, [appName])

  const contextValue = useMemo(
    () => ({
      appName,
      tenantName,
      status,
      refreshSettings,
    }),
    [
      appName,
      tenantName,
      status,
      refreshSettings,
    ],
  )

  return (
    <AppSettingsContext.Provider
      value={contextValue}
    >
      {children}
    </AppSettingsContext.Provider>
  )
}
