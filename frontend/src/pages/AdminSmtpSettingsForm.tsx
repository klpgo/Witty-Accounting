import {
  type FormEvent,
  useCallback,
  useEffect,
  useState,
} from 'react'
import { useNavigate } from 'react-router-dom'

import {
  getSmtpSettings,
  SettingsApiError,
  testSmtpSettings,
  updateSmtpSettings,
} from '../api/settings'

import { getAccessToken } from '../auth/tokenStorage'
import { useAuth } from '../auth/useAuth'

function AdminSmtpSettingsForm() {
  const navigate = useNavigate()
  const { signOut } = useAuth()

  const [
    useDatabaseSettings,
    setUseDatabaseSettings,
  ] = useState(false)
  const [
    mailSendingEnabled,
    setMailSendingEnabled,
  ] = useState(true)
  const [smtpHost, setSmtpHost] = useState('')
  const [smtpPort, setSmtpPort] = useState('')
  const [
    smtpTimeoutSeconds,
    setSmtpTimeoutSeconds,
  ] = useState('')
  const [smtpStarttls, setSmtpStarttls] =
    useState(false)
  const [smtpUsername, setSmtpUsername] =
    useState('')
  const [smtpPassword, setSmtpPassword] =
    useState('')
  const [
    smtpPasswordConfigured,
    setSmtpPasswordConfigured,
  ] = useState(false)
  const [
    clearSmtpPassword,
    setClearSmtpPassword,
  ] = useState(false)
  const [
    mailFromAddress,
    setMailFromAddress,
  ] = useState('')
  const [mailFromName, setMailFromName] =
    useState('')

  const [isLoading, setIsLoading] =
    useState(true)
  const [isSaving, setIsSaving] =
    useState(false)
  const [isTesting, setIsTesting] =
    useState(false)
  const [
    errorMessage,
    setErrorMessage,
  ] = useState<string | null>(null)
  const [
    successMessage,
    setSuccessMessage,
  ] = useState<string | null>(null)

  const handleUnauthorized = useCallback((): void => {
    signOut()

    navigate('/login', {
      replace: true,
    })
  }, [navigate, signOut])

  useEffect(() => {
    const controller = new AbortController()

    async function loadSettings(): Promise<void> {
      const accessToken = getAccessToken()

      if (accessToken === null) {
        handleUnauthorized()
        return
      }

      setIsLoading(true)
      setErrorMessage(null)

      try {
        const loadedSettings =
          await getSmtpSettings(
            accessToken,
            controller.signal,
          )

        setUseDatabaseSettings(
          loadedSettings
            .smtp_use_database_settings,
        )
        setMailSendingEnabled(
          loadedSettings.mail_sending_enabled,
        )
        setSmtpHost(loadedSettings.smtp_host)
        setSmtpPort(
          String(loadedSettings.smtp_port),
        )
        setSmtpTimeoutSeconds(
          loadedSettings.smtp_timeout_seconds,
        )
        setSmtpStarttls(
          loadedSettings.smtp_starttls,
        )
        setSmtpUsername(
          loadedSettings.smtp_username ?? '',
        )
        setSmtpPasswordConfigured(
          loadedSettings
            .smtp_password_configured,
        )
        setMailFromAddress(
          loadedSettings.mail_from_address,
        )
        setMailFromName(
          loadedSettings.mail_from_name,
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
            : 'Die Mailserver-Einstellungen konnten nicht geladen werden.',
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
  }, [handleUnauthorized])

  async function handleSubmit(
    event: FormEvent<HTMLFormElement>,
  ): Promise<void> {
    event.preventDefault()

    const normalizedHost = smtpHost.trim()
    const normalizedUsername =
      smtpUsername.trim()
    const normalizedFromAddress =
      mailFromAddress.trim()
    const normalizedFromName =
      mailFromName.trim()
    const port = Number(smtpPort)
    const timeout = Number(
      smtpTimeoutSeconds
        .trim()
        .replace(',', '.'),
    )

    setErrorMessage(null)
    setSuccessMessage(null)

    if (useDatabaseSettings) {
      if (!normalizedHost) {
        setErrorMessage(
          'Der SMTP-Host darf nicht leer sein.',
        )
        return
      }

      if (
        !Number.isInteger(port) ||
        port < 1 ||
        port > 65535
      ) {
        setErrorMessage(
          'Der SMTP-Port muss zwischen 1 und 65535 liegen.',
        )
        return
      }

      if (
        !Number.isFinite(timeout) ||
        timeout <= 0 ||
        timeout > 300
      ) {
        setErrorMessage(
          'Der SMTP-Timeout muss größer als 0 und höchstens 300 Sekunden sein.',
        )
        return
      }

      if (!normalizedFromName) {
        setErrorMessage(
          'Der Absendername darf nicht leer sein.',
        )
        return
      }

      if (
        !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(
          normalizedFromAddress,
        )
      ) {
        setErrorMessage(
          'Bitte gib eine gültige Absenderadresse ein.',
        )
        return
      }

      if (
        normalizedUsername &&
        !smtpPasswordConfigured &&
        !smtpPassword
      ) {
        setErrorMessage(
          'Für den SMTP-Benutzernamen ist ein Passwort erforderlich.',
        )
        return
      }
    }

    const accessToken = getAccessToken()

    if (accessToken === null) {
      handleUnauthorized()
      return
    }

    setIsSaving(true)

    try {
      const updatedSettings =
        await updateSmtpSettings(
          accessToken,
          {
            smtp_use_database_settings:
              useDatabaseSettings,
            mail_sending_enabled:
              mailSendingEnabled,
            smtp_host: normalizedHost,
            smtp_port: port,
            smtp_timeout_seconds:
              String(timeout),
            smtp_starttls: smtpStarttls,
            smtp_username:
              normalizedUsername || null,
            ...(smtpPassword
              ? {
                  smtp_password:
                    smtpPassword,
                }
              : {}),
            clear_smtp_password:
              clearSmtpPassword,
            mail_from_address:
              normalizedFromAddress,
            mail_from_name:
              normalizedFromName,
          },
        )

      setUseDatabaseSettings(
        updatedSettings
          .smtp_use_database_settings,
      )
      setMailSendingEnabled(
        updatedSettings.mail_sending_enabled,
      )
      setSmtpHost(updatedSettings.smtp_host)
      setSmtpPort(
        String(updatedSettings.smtp_port),
      )
      setSmtpTimeoutSeconds(
        updatedSettings.smtp_timeout_seconds,
      )
      setSmtpStarttls(
        updatedSettings.smtp_starttls,
      )
      setSmtpUsername(
        updatedSettings.smtp_username ?? '',
      )
      setSmtpPassword('')
      setSmtpPasswordConfigured(
        updatedSettings
          .smtp_password_configured,
      )
      setClearSmtpPassword(false)
      setMailFromAddress(
        updatedSettings.mail_from_address,
      )
      setMailFromName(
        updatedSettings.mail_from_name,
      )

      setSuccessMessage(
        'Die Mailserver-Einstellungen wurden gespeichert.',
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
          : 'Die Mailserver-Einstellungen konnten nicht gespeichert werden.',
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
      const result = await testSmtpSettings(
        accessToken,
      )

      setSuccessMessage(
        `Die Testmail wurde an ${result.recipient_email} gesendet.`,
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
          : 'Die SMTP-Testnachricht konnte nicht versendet werden.',
      )
    } finally {
      setIsTesting(false)
    }
  }

  if (isLoading) {
    return (
      <section className="card">
        <p className="muted">
          Mailserver-Einstellungen werden geladen …
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
          <h2>Mailserver</h2>

          <p className="muted">
            SMTP-Versand und Absender für
            Rechnungs-E-Mails verwalten.
          </p>
        </div>

        {errorMessage && (
          <div
            className="form-error"
            role="alert"
          >
            {errorMessage}
          </div>
        )}

        {successMessage && (
          <div
            className="form-success"
            role="status"
          >
            {successMessage}
          </div>
        )}

        <div className="form-grid settings-business-grid">
          <label className="form-field">
            <span>Konfigurationsquelle</span>

            <select
              value={
                useDatabaseSettings
                  ? 'database'
                  : 'environment'
              }
              onChange={(event) => {
                setUseDatabaseSettings(
                  event.target.value ===
                    'database',
                )
              }}
            >
              <option value="environment">
                Umgebung (.env)
              </option>
              <option value="database">
                Admin-Einstellungen
              </option>
            </select>
          </label>

          <label className="form-field settings-checkbox-field">
            <span>E-Mail-Versand</span>

            <span className="settings-checkbox-control">
              <input
                type="checkbox"
                checked={mailSendingEnabled}
                onChange={(event) => {
                  setMailSendingEnabled(
                    event.target.checked,
                  )
                }}
              />

              Rechnungs-E-Mails dürfen
              versendet werden
            </span>
          </label>

          <label className="form-field">
            <span>SMTP-Host</span>

            <input
              type="text"
              value={smtpHost}
              maxLength={255}
              disabled={!useDatabaseSettings}
              onChange={(event) => {
                setSmtpHost(event.target.value)
              }}
              required={useDatabaseSettings}
            />
          </label>

          <label className="form-field">
            <span>SMTP-Port</span>

            <input
              type="number"
              min="1"
              max="65535"
              step="1"
              value={smtpPort}
              disabled={!useDatabaseSettings}
              onChange={(event) => {
                setSmtpPort(event.target.value)
              }}
              required={useDatabaseSettings}
            />
          </label>

          <label className="form-field">
            <span>Timeout in Sekunden</span>

            <input
              type="text"
              inputMode="decimal"
              value={smtpTimeoutSeconds}
              disabled={!useDatabaseSettings}
              onChange={(event) => {
                setSmtpTimeoutSeconds(
                  event.target.value,
                )
              }}
              required={useDatabaseSettings}
            />
          </label>

          <label className="form-field settings-checkbox-field">
            <span>Transportverschlüsselung</span>

            <span className="settings-checkbox-control">
              <input
                type="checkbox"
                checked={smtpStarttls}
                disabled={!useDatabaseSettings}
                onChange={(event) => {
                  setSmtpStarttls(
                    event.target.checked,
                  )
                }}
              />

              STARTTLS verwenden
            </span>
          </label>

          <label className="form-field">
            <span>SMTP-Benutzername</span>

            <input
              type="text"
              value={smtpUsername}
              maxLength={255}
              autoComplete="username"
              disabled={!useDatabaseSettings}
              onChange={(event) => {
                setSmtpUsername(
                  event.target.value,
                )
              }}
            />
          </label>

          <label className="form-field">
          <div className="form-field settings-password-field">
            <span id="smtp-password-label">
              SMTP-Passwort
            </span>

            <input
              type="password"
              value={smtpPassword}
              aria-labelledby="smtp-password-label"
              autoComplete="new-password"
              disabled={
                !useDatabaseSettings ||
                clearSmtpPassword
              }
              onChange={(event) => {
                setSmtpPassword(
                  event.target.value,
                )
              }}
            />

            <small className="muted">
              {smtpPasswordConfigured
                ? 'Ein Passwort ist gespeichert. Leer lassen, um es beizubehalten.'
                : 'Es ist noch kein Passwort gespeichert.'}
            </small>

            <label className="settings-checkbox-control settings-password-clear-control">
              <input
                type="checkbox"
                checked={clearSmtpPassword}
                disabled={
                  !useDatabaseSettings ||
                  !smtpPasswordConfigured
                }
                onChange={(event) => {
                  setClearSmtpPassword(
                    event.target.checked,
                  )

                  if (event.target.checked) {
                    setSmtpPassword('')
                  }
                }}
              />

              Gespeichertes Passwort beim Speichern
              löschen
            </label>
          </div>
          </label>

          <label className="form-field settings-smtp-sender-field">
            <span>Absendername</span>

            <input
              type="text"
              value={mailFromName}
              maxLength={255}
              disabled={!useDatabaseSettings}
              onChange={(event) => {
                setMailFromName(
                  event.target.value,
                )
              }}
              required={useDatabaseSettings}
            />
          </label>

          <label className="form-field">
            <span>Absenderadresse</span>

            <input
              type="email"
              value={mailFromAddress}
              maxLength={320}
              autoComplete="email"
              disabled={!useDatabaseSettings}
              onChange={(event) => {
                setMailFromAddress(
                  event.target.value,
                )
              }}
              required={useDatabaseSettings}
            />
          </label>
        </div>
      </section>

      <div className="settings-actions">
        <button
          className="button button-primary"
          type="submit"
          disabled={isSaving || isTesting}
        >
          {isSaving
            ? 'Mailserver wird gespeichert …'
            : 'Mailserver speichern'}
        </button>

        <button
          className="button"
          type="button"
          disabled={isSaving || isTesting}
          onClick={() => {
            void handleTest()
          }}
        >
          {isTesting
            ? 'Testmail wird versendet …'
            : 'Mailserver testen'}
        </button>
      </div>

      <p className="muted">
        Der Test verwendet die zuletzt gespeicherten
        Einstellungen und sendet die Nachricht an die
        E-Mail-Adresse des angemeldeten Administrators.
      </p>
    </form>
  )
}

export default AdminSmtpSettingsForm
