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


function AdminInvoiceExportSettingsForm() {
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
            : 'Die SFTP-Einstellungen konnten nicht geladen werden.',
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
        'Der SFTP-Host darf nicht leer sein.',
      )
      return
    }

    if (
      !Number.isInteger(portNumber) ||
      portNumber < 1 ||
      portNumber > 65535
    ) {
      setErrorMessage(
        'Der SFTP-Port muss zwischen 1 und 65535 liegen.',
      )
      return
    }

    if (!normalizedUsername) {
      setErrorMessage(
        'Der SFTP-Benutzer darf nicht leer sein.',
      )
      return
    }

    if (!normalizedDirectory.startsWith('/')) {
      setErrorMessage(
        'Das Zielverzeichnis muss ein absoluter Pfad sein.',
      )
      return
    }

    if (
      enabled &&
      (!privateKeyConfigured || !knownHostsConfigured)
    ) {
      setErrorMessage(
        'Vor dem Aktivieren müssen privater Schlüssel und known_hosts eingerichtet sein.',
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
        'Die SFTP-Exporteinstellungen wurden gespeichert.',
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
          : 'Die SFTP-Einstellungen konnten nicht gespeichert werden.',
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
        `SFTP-Verbindung zu ${result.host} und Zugriff auf ${result.directory} erfolgreich.`,
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
          : 'Die SFTP-Verbindung konnte nicht getestet werden.',
      )
    } finally {
      setIsTesting(false)
    }
  }

  if (isLoading) {
    return (
      <section className="card">
        <p className="muted">
          SFTP-Einstellungen werden geladen …
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
          <h2>Rechnungsexport per SFTP</h2>

          <p className="muted">
            Finalisierte, archivierte PDF-Rechnungen
            können vom Rechnungsdialog aus manuell
            exportiert werden. Auf dem Zielserver wird
            automatisch ein Jahresverzeichnis angelegt.
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

          <span>SFTP-Rechnungsexport aktivieren</span>
        </label>

        <div className="form-grid settings-business-grid">
          <label className="form-field">
            <span>SFTP-Host</span>
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
            <span>Port</span>
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
            <span>Benutzer</span>
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
            <span>Zielverzeichnis</span>
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
            Privater Schlüssel:{' '}
            <strong>
              {privateKeyConfigured
                ? 'eingerichtet'
                : 'nicht eingerichtet'}
            </strong>
          </p>
          <p>
            known_hosts:{' '}
            <strong>
              {knownHostsConfigured
                ? 'eingerichtet'
                : 'nicht eingerichtet'}
            </strong>
          </p>
        </div>

        <p className="muted">
          Der private Schlüssel und known_hosts werden
          aus read-only Dateien im Container gelesen und
          niemals in der Datenbank gespeichert.
        </p>
      </section>

      <div className="settings-actions">
        <button
          className="button button-primary"
          type="submit"
          disabled={isSaving || isTesting}
        >
          {isSaving
            ? 'SFTP-Einstellungen werden gespeichert …'
            : 'SFTP-Einstellungen speichern'}
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
            ? 'Verbindung wird getestet …'
            : 'Verbindung testen'}
        </button>
      </div>
    </form>
  )
}

export default AdminInvoiceExportSettingsForm
