import {
  type FormEvent,
  useCallback,
  useEffect,
  useState,
} from 'react'
import { useNavigate } from 'react-router-dom'

import {
  getInvoiceExportSettings,
  SettingsApiError,
  testInvoiceExportSettings,
  updateInvoiceExportSettings,
} from '../api/settings'
import { getAccessToken } from '../auth/tokenStorage'
import { useAuth } from '../auth/useAuth'
import { useTranslation } from '../i18n/useTranslation'


function AdminInvoiceExportSettingsForm() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const { signOut } = useAuth()

  const [enabled, setEnabled] = useState(false)
  const [host, setHost] = useState('')
  const [port, setPort] = useState('22')
  const [username, setUsername] = useState('')
  const [directory, setDirectory] = useState('')
  const [privateKeyConfigured, setPrivateKeyConfigured] =
    useState(false)
  const [knownHostsConfigured, setKnownHostsConfigured] =
    useState(false)
  const [isLoading, setIsLoading] = useState(true)
  const [isSaving, setIsSaving] = useState(false)
  const [isTesting, setIsTesting] = useState(false)
  const [errorMessage, setErrorMessage] =
    useState<string | null>(null)
  const [successMessage, setSuccessMessage] =
    useState<string | null>(null)

  const handleUnauthorized = useCallback((): void => {
    signOut()
    navigate('/login', { replace: true })
  }, [navigate, signOut])

  const applySettings = useCallback((settings: {
    enabled: boolean
    host: string | null
    port: number
    username: string | null
    directory: string | null
    private_key_configured: boolean
    known_hosts_configured: boolean
  }): void => {
    setEnabled(settings.enabled)
    setHost(settings.host ?? '')
    setPort(String(settings.port))
    setUsername(settings.username ?? '')
    setDirectory(settings.directory ?? '')
    setPrivateKeyConfigured(
      settings.private_key_configured,
    )
    setKnownHostsConfigured(
      settings.known_hosts_configured,
    )
  }, [])

  useEffect(() => {
    const controller = new AbortController()

    async function loadSettings(): Promise<void> {
      const accessToken = getAccessToken()

      if (accessToken === null) {
        handleUnauthorized()
        return
      }

      try {
        applySettings(
          await getInvoiceExportSettings(
            accessToken,
            controller.signal,
          ),
        )
      } catch (error) {
        if (
          error instanceof DOMException &&
          error.name === 'AbortError'
        ) {
          return
        }

        if (
          error instanceof SettingsApiError &&
          error.status === 401
        ) {
          handleUnauthorized()
          return
        }

        setErrorMessage(
          error instanceof Error
            ? error.message
            : t('settings.export.loadFailed'),
        )
      } finally {
        if (!controller.signal.aborted) {
          setIsLoading(false)
        }
      }
    }

    void loadSettings()

    return () => {
      controller.abort()
    }
  }, [applySettings, handleUnauthorized])

  async function handleSubmit(
    event: FormEvent<HTMLFormElement>,
  ): Promise<void> {
    event.preventDefault()

    const normalizedHost = host.trim()
    const normalizedUsername = username.trim()
    const normalizedDirectory = directory.trim()
    const portNumber = Number(port)

    setErrorMessage(null)
    setSuccessMessage(null)

    if (!normalizedHost) {
      setErrorMessage(
        t('settings.export.hostMissing'),
      )
      return
    }

    if (
      !Number.isInteger(portNumber) ||
      portNumber < 1 ||
      portNumber > 65535
    ) {
      setErrorMessage(
        t('settings.export.portRange'),
      )
      return
    }

    if (!normalizedUsername) {
      setErrorMessage(
        t('settings.export.userMissing'),
      )
      return
    }

    if (!normalizedDirectory.startsWith('/')) {
      setErrorMessage(
        t('settings.export.directoryAbsolute'),
      )
      return
    }

    if (
      enabled &&
      (!privateKeyConfigured || !knownHostsConfigured)
    ) {
      setErrorMessage(
        t('settings.export.keysMissing'),
      )
      return
    }

    const accessToken = getAccessToken()

    if (accessToken === null) {
      handleUnauthorized()
      return
    }

    setIsSaving(true)

    try {
      const updatedSettings =
        await updateInvoiceExportSettings(
          accessToken,
          {
            enabled,
            host: normalizedHost,
            port: portNumber,
            username: normalizedUsername,
            directory: normalizedDirectory,
          },
        )

      applySettings(updatedSettings)
      setSuccessMessage(
        t('settings.export.saved'),
      )
    } catch (error) {
      if (
        error instanceof SettingsApiError &&
        error.status === 401
      ) {
        handleUnauthorized()
        return
      }

      setErrorMessage(
        error instanceof Error
          ? error.message
          : t('settings.export.saveFailed'),
      )
    } finally {
      setIsSaving(false)
    }
  }

  async function handleTest(): Promise<void> {
    const accessToken = getAccessToken()

    if (accessToken === null) {
      handleUnauthorized()
      return
    }

    setIsTesting(true)
    setErrorMessage(null)
    setSuccessMessage(null)

    try {
      const result = await testInvoiceExportSettings(
        accessToken,
      )

      setSuccessMessage(
        t('settings.export.testSucceeded', {
          host: result.host,
          directory: result.directory,
        }),
      )
    } catch (error) {
      if (
        error instanceof SettingsApiError &&
        error.status === 401
      ) {
        handleUnauthorized()
        return
      }

      setErrorMessage(
        error instanceof Error
          ? error.message
          : t('settings.export.testFailed'),
      )
    } finally {
      setIsTesting(false)
    }
  }

  if (isLoading) {
    return (
      <section className="card">
        <p className="muted">
          {t('settings.export.loading')}
        </p>
      </section>
    )
  }

  return (
    <form
      className="card settings-form"
      onSubmit={handleSubmit}
    >
      <section className="settings-section">
        <div>
          <h2>{t('settings.export.title')}</h2>

          <p className="muted">
            {t('settings.export.intro')}
          </p>
        </div>

        {errorMessage && (
          <div className="form-error" role="alert">
            {errorMessage}
          </div>
        )}

        {successMessage && (
          <div className="form-success" role="status">
            {successMessage}
          </div>
        )}

        <label className="checkbox-field">
          <input
            type="checkbox"
            checked={enabled}
            onChange={(event) => {
              setEnabled(event.target.checked)
            }}
          />

          <span>{t('settings.export.enable')}</span>
        </label>

        <div className="form-grid settings-business-grid">
          <label className="form-field">
            <span>{t('settings.export.host')}</span>
            <input
              type="text"
              value={host}
              maxLength={255}
              onChange={(event) => {
                setHost(event.target.value)
              }}
              required
            />
          </label>

          <label className="form-field">
            <span>{t('settings.export.port')}</span>
            <input
              type="number"
              min="1"
              max="65535"
              step="1"
              value={port}
              onChange={(event) => {
                setPort(event.target.value)
              }}
              required
            />
          </label>

          <label className="form-field">
            <span>{t('settings.export.user')}</span>
            <input
              type="text"
              value={username}
              maxLength={255}
              autoComplete="off"
              onChange={(event) => {
                setUsername(event.target.value)
              }}
              required
            />
          </label>

          <label className="form-field settings-wide-field">
            <span>{t('settings.export.directory')}</span>
            <input
              type="text"
              value={directory}
              maxLength={1024}
              placeholder="/rechnungseingang"
              onChange={(event) => {
                setDirectory(event.target.value)
              }}
              required
            />
          </label>
        </div>

        <div className="settings-secret-status">
          <p>
            {t('settings.export.privateKey', { status: '' })}
            <strong>
              {privateKeyConfigured
                ? t('settings.common.configured')
                : t('settings.common.notConfigured')}
            </strong>
          </p>
          <p>
            {t('settings.export.knownHosts', { status: '' })}
            <strong>
              {knownHostsConfigured
                ? t('settings.common.configured')
                : t('settings.common.notConfigured')}
            </strong>
          </p>
        </div>

        <p className="muted">
          {t('settings.export.keysHint')}
        </p>
      </section>

      <div className="settings-actions">
        <button
          className="button button-primary"
          type="submit"
          disabled={isSaving || isTesting}
        >
          {isSaving
            ? t('settings.export.saving')
            : t('settings.export.save')}
        </button>

        <button
          className="button button-secondary"
          type="button"
          disabled={
            isSaving ||
            isTesting ||
            !enabled
          }
          onClick={() => {
            void handleTest()
          }}
        >
          {isTesting
            ? t('settings.common.testingConnection')
            : t('settings.common.testConnection')}
        </button>
      </div>
    </form>
  )
}

export default AdminInvoiceExportSettingsForm
