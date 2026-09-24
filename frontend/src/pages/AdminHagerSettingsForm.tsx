import {
  type FormEvent,
  useCallback,
  useEffect,
  useState,
} from 'react'
import { useNavigate } from 'react-router-dom'

import {
  getHagerSettings,
  type HagerAutoImportStatus,
  type HagerSettings,
  type HagerSettingsUpdate,
  SettingsApiError,
  testHagerSettings,
  updateHagerSettings,
} from '../api/settings'
import { getAccessToken } from '../auth/tokenStorage'
import { useAuth } from '../auth/useAuth'


function formatLocalDateTime(
  value: string | null,
): string | null {
  // Witty liefert lokale Zeit ohne Zeitzone: 2026-07-15T11:26:37
  const match = value?.match(
    /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/,
  )

  if (!match) {
    return null
  }

  const [, year, month, day, hour, minute] = match

  return `${day}.${month}.${year} ${hour}:${minute} Uhr`
}


function formatTimestamp(value: string | null): string | null {
  if (!value) {
    return null
  }

  const date = new Date(value)

  if (Number.isNaN(date.getTime())) {
    return null
  }

  return (
    date.toLocaleString('de-DE', {
      timeZone: 'Europe/Berlin',
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    }) + ' Uhr'
  )
}


const STATUS_LABELS: Record<HagerAutoImportStatus, string> = {
  running: 'läuft',
  success: 'erfolgreich',
  error: 'fehlgeschlagen',
}


function AdminHagerSettingsForm() {
  const navigate = useNavigate()
  const { signOut } = useAuth()

  const [username, setUsername] = useState('')
  const [installationId, setInstallationId] = useState('')
  const [password, setPassword] = useState('')
  const [clearPassword, setClearPassword] = useState(false)
  const [passwordConfigured, setPasswordConfigured] =
    useState(false)
  const [isLoading, setIsLoading] = useState(true)
  const [isSaving, setIsSaving] = useState(false)
  const [isTesting, setIsTesting] = useState(false)
  const [savedComplete, setSavedComplete] = useState(false)
  const [autoEnabled, setAutoEnabled] = useState(false)
  const [autoInterval, setAutoInterval] = useState('24')
  const [autoStartTime, setAutoStartTime] = useState('03:00')
  const [autoStatus, setAutoStatus] =
    useState<HagerSettings | null>(null)
  const [errorMessage, setErrorMessage] =
    useState<string | null>(null)
  const [successMessage, setSuccessMessage] =
    useState<string | null>(null)

  const handleUnauthorized = useCallback((): void => {
    signOut()
    navigate('/login', { replace: true })
  }, [navigate, signOut])

  const applySettings = useCallback(
    (settings: HagerSettings): void => {
      setUsername(settings.username ?? '')
      setInstallationId(settings.installation_id ?? '')
      setPasswordConfigured(settings.password_configured)
      setSavedComplete(
        Boolean(settings.username) &&
          Boolean(settings.installation_id) &&
          settings.password_configured,
      )
      setPassword('')
      setClearPassword(false)
      setAutoEnabled(settings.auto_import_enabled)
      setAutoInterval(String(settings.auto_import_interval_hours))
      setAutoStartTime(settings.auto_import_start_time)
      setAutoStatus(settings)
    },
    [],
  )

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
          await getHagerSettings(
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
            : 'Die Hager-Einstellungen konnten nicht geladen werden.',
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

    const normalizedInstallationId = installationId.trim()

    setErrorMessage(null)
    setSuccessMessage(null)

    if (
      normalizedInstallationId &&
      !/^\d+$/.test(normalizedInstallationId)
    ) {
      setErrorMessage(
        'Die Installations-ID besteht nur aus Ziffern.',
      )
      return
    }

    const intervalHours = Number(autoInterval)

    if (
      !Number.isInteger(intervalHours) ||
      intervalHours < 1 ||
      intervalHours > 24
    ) {
      setErrorMessage(
        'Das Intervall muss zwischen 1 und 24 Stunden liegen.',
      )
      return
    }

    if (!/^([01]\d|2[0-3]):[0-5]\d$/.test(autoStartTime)) {
      setErrorMessage(
        'Bitte eine gültige Startzeit (HH:MM) angeben.',
      )
      return
    }

    const accessToken = getAccessToken()

    if (accessToken === null) {
      handleUnauthorized()
      return
    }

    const payload: HagerSettingsUpdate = {
      username: username.trim(),
      installation_id: normalizedInstallationId,
      auto_import_enabled: autoEnabled,
      auto_import_interval_hours: intervalHours,
      auto_import_start_time: autoStartTime,
    }

    if (clearPassword) {
      payload.clear_password = true
    } else if (password) {
      payload.password = password
    }

    setIsSaving(true)

    try {
      applySettings(
        await updateHagerSettings(
          accessToken,
          payload,
        ),
      )
      setSuccessMessage(
        'Die Hager-Zugangsdaten wurden gespeichert.',
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
          : 'Die Hager-Einstellungen konnten nicht gespeichert werden.',
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
      const result = await testHagerSettings(accessToken)
      const latest = formatLocalDateTime(
        result.latest_session_start,
      )

      setSuccessMessage(
        `Verbindung zu Hager flow erfolgreich: ${result.sessions} ` +
          'Ladevorgänge verfügbar' +
          (latest ? `, der neueste vom ${latest}.` : '.'),
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
          : 'Die Verbindung zu Hager flow konnte nicht getestet werden.',
      )
    } finally {
      setIsTesting(false)
    }
  }

  if (isLoading) {
    return (
      <section className="card">
        <p className="muted">
          Hager-Einstellungen werden geladen …
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
          <h2>Hager flow</h2>

          <p className="muted">
            Zugangsdaten für das Hager-flow-Portal,
            aus dem die Ladevorgänge abgerufen werden.
            Das Passwort wird verschlüsselt gespeichert
            und nie wieder angezeigt.
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

        <div className="form-grid settings-business-grid">
          <label className="form-field">
            <span>Benutzername (E-Mail)</span>
            <input
              type="text"
              value={username}
              maxLength={320}
              autoComplete="off"
              onChange={(event) => {
                setUsername(event.target.value)
              }}
            />
          </label>

          <label className="form-field">
            <span>Installations-ID</span>
            <input
              type="text"
              inputMode="numeric"
              value={installationId}
              maxLength={50}
              placeholder="z. B. 1000143617"
              onChange={(event) => {
                setInstallationId(event.target.value)
              }}
            />
          </label>

          <div className="form-field settings-password-field">
            <span id="hager-password-label">
              Passwort
            </span>

            <input
              type="password"
              value={password}
              aria-labelledby="hager-password-label"
              autoComplete="new-password"
              disabled={clearPassword}
              onChange={(event) => {
                setPassword(event.target.value)
              }}
            />

            <small className="muted">
              {passwordConfigured
                ? 'Ein Passwort ist gespeichert. Leer lassen, um es beizubehalten.'
                : 'Es ist noch kein Passwort gespeichert.'}
            </small>

            <label className="settings-checkbox-control settings-password-clear-control">
              <input
                type="checkbox"
                checked={clearPassword}
                disabled={!passwordConfigured}
                onChange={(event) => {
                  setClearPassword(event.target.checked)

                  if (event.target.checked) {
                    setPassword('')
                  }
                }}
              />

              Gespeichertes Passwort beim Speichern
              löschen
            </label>
          </div>
        </div>

        <p className="muted">
          Die Installations-ID steht in der Adresse der
          Hager-flow-Seite: flow.hager.com/e-mobility/
          <strong>Installations-ID</strong>/…
        </p>
      </section>

      <section className="settings-section">
        <div>
          <h2>Automatischer Abruf</h2>

          <p className="muted">
            Ruft neue Ladevorgänge regelmäßig aus Hager flow ab,
            alle N Stunden ab der Startzeit (deutsche Ortszeit),
            mindestens einmal täglich. Nach dem Aktivieren erfolgt
            der erste Abruf innerhalb einer Minute.
          </p>
        </div>

        <label className="settings-checkbox-control">
          <input
            type="checkbox"
            checked={autoEnabled}
            disabled={!savedComplete && !autoEnabled}
            onChange={(event) => {
              setAutoEnabled(event.target.checked)
            }}
          />
          Automatischen Abruf aktivieren
        </label>

        {!savedComplete && (
          <small className="muted">
            Zuerst Benutzername, Passwort und Installations-ID
            speichern.
          </small>
        )}

        <div className="form-grid settings-business-grid">
          <label className="form-field">
            <span>Alle … Stunden</span>
            <input
              type="number"
              min={1}
              max={24}
              step={1}
              value={autoInterval}
              disabled={!autoEnabled}
              onChange={(event) => {
                setAutoInterval(event.target.value)
              }}
            />
          </label>

          <label className="form-field">
            <span>Beginnend um</span>
            <input
              type="time"
              value={autoStartTime}
              disabled={!autoEnabled}
              onChange={(event) => {
                setAutoStartTime(event.target.value)
              }}
            />
          </label>
        </div>

        {autoStatus && (
          <dl className="settings-status-list">
            {autoStatus.auto_import_enabled &&
              autoStatus.auto_import_next_run_at && (
                <div>
                  <dt>Nächster Abruf</dt>
                  <dd>
                    {formatTimestamp(
                      autoStatus.auto_import_next_run_at,
                    )}
                  </dd>
                </div>
              )}

            {autoStatus.last_successful_fetch_at && (
              <div>
                <dt>Letzter erfolgreicher Abruf</dt>
                <dd>
                  {formatTimestamp(
                    autoStatus.last_successful_fetch_at,
                  )}
                  {' '}
                  (manuell oder automatisch)
                </dd>
              </div>
            )}

            <div>
              <dt>Letzter automatischer Abruf</dt>
              <dd>
                {autoStatus.auto_import_last_started_at
                  ? `${formatTimestamp(
                      autoStatus.auto_import_last_started_at,
                    )} – ${
                      autoStatus.auto_import_last_status
                        ? STATUS_LABELS[
                            autoStatus.auto_import_last_status
                          ]
                        : 'unbekannt'
                    }`
                  : 'noch nicht erfolgt'}
              </dd>
            </div>

            {autoStatus.auto_import_last_message && (
              <div>
                <dt>Ergebnis</dt>
                <dd
                  className={
                    autoStatus.auto_import_last_status === 'error'
                      ? 'form-error'
                      : undefined
                  }
                >
                  {autoStatus.auto_import_last_message}
                </dd>
              </div>
            )}
          </dl>
        )}
      </section>

      <div className="settings-actions">
        <button
          className="button button-primary"
          type="submit"
          disabled={isSaving || isTesting}
        >
          {isSaving
            ? 'Hager-Zugangsdaten werden gespeichert …'
            : 'Hager-Zugangsdaten speichern'}
        </button>

        <button
          className="button button-secondary"
          type="button"
          disabled={
            isSaving ||
            isTesting ||
            !savedComplete
          }
          title={
            savedComplete
              ? undefined
              : 'Zuerst Benutzername, Passwort und Installations-ID speichern.'
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

export default AdminHagerSettingsForm
