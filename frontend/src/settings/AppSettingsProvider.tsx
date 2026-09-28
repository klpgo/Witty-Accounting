import {
  type ReactNode,
  useCallback,
  useEffect,
  useMemo,
  useState,
} from 'react'

import { getPublicSettings } from '../api/settings'
import {
  setDisplayLocale,
  setDisplayTimeZone,
} from '../utils/dateFormat'
import { setNumberFormat } from '../utils/numberFormat'
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
  const [defaultLanguage, setDefaultLanguage] =
    useState('de')

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
        setDefaultLanguage(
          publicSettings.default_language ?? 'de',
        )

        if (publicSettings.timezone) {
          setDisplayTimeZone(publicSettings.timezone)
        }

        if (publicSettings.locale) {
          setDisplayLocale(publicSettings.locale)
          setNumberFormat(
            publicSettings.locale,
            publicSettings.currency ?? 'EUR',
          )
        }
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
      defaultLanguage,
      status,
      refreshSettings,
    }),
    [
      appName,
      tenantName,
      defaultLanguage,
      status,
      refreshSettings,
    ],
  )

  return (
    <AppSettingsContext.Provider
      value={contextValue}
    >
      {/* erst rendern, wenn Gebietsschema, Währung und Zeitzone feststehen */}
      {status === 'ready' ? children : null}
    </AppSettingsContext.Provider>
  )
}
