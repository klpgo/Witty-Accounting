import {
  type FormEvent,
  useCallback,
  useEffect,
  useState,
} from 'react'
import { useNavigate } from 'react-router-dom'

import {
  getHagerSettings,
  type HagerSettings,
  type HagerSettingsUpdate,
  SettingsApiError,
  testHagerSettings,
  updateHagerSettings,
} from '../api/settings'
import { getAccessToken } from '../auth/tokenStorage'
import { useAuth } from '../auth/useAuth'
import { useTranslation } from '../i18n/useTranslation'


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


function AdminHagerSettingsForm() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const { signOut } = useAuth()

  const [username, setUsername] = useState('')
  const [installationId, setInstallationId] = useState('')
  const [serialNumber, setSerialNumber] = useState('')
  const [skipEmptySessions, setSkipEmptySessions] =
    useState(false)
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
      setSerialNumber(settings.serial_number ?? '')
      setSkipEmptySessions(settings.skip_empty_sessions)
      setPasswordConfigured(settings.password_configured)
      setSavedComplete(
        Boolean(settings.username) &&
          Boolean(settings.installation_id) &&
          Boolean(settings.serial_number) &&
          settings.password_configured,
      )
      setPassword('')
      setClearPassword(false)
      setAutoEnabled(settings.auto_import_enabled)
      setAutoInterval(String(settings.auto_import_interval_hours))
      setAutoStartTime(settings.auto_import_start_time)
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
            : t('settings.hager.loadFailed'),
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
    const normalizedSerialNumber = serialNumber.trim()

    setErrorMessage(null)
    setSuccessMessage(null)

    if (
      normalizedInstallationId &&
      !/^\d+$/.test(normalizedInstallationId)
    ) {
      setErrorMessage(
        t('settings.hager.installationDigits'),
      )
      return
    }

    if (
      normalizedSerialNumber &&
      !/^\d+$/.test(normalizedSerialNumber)
    ) {
      setErrorMessage(
        t('settings.hager.serialDigits'),
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
        t('settings.hager.intervalRange'),
      )
      return
    }

    if (!/^([01]\d|2[0-3]):[0-5]\d$/.test(autoStartTime)) {
      setErrorMessage(
        t('settings.hager.startTimeInvalid'),
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
      serial_number: normalizedSerialNumber,
      skip_empty_sessions: skipEmptySessions,
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
        t('settings.hager.saved'),
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
          : t('settings.hager.saveFailed'),
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
        [
          t('settings.hager.testSucceeded'),
          result.sessions !== null
            ? t('settings.hager.testSessions', { count: result.sessions })
            : null,
          latest
            ? t('settings.hager.testLatest', { date: latest })
            : t('settings.hager.testNoSessions'),
        ]
          .filter(Boolean)
          .join(' '),
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
          : t('settings.hager.testFailed'),
      )
    } finally {
      setIsTesting(false)
    }
  }

  if (isLoading) {
    return (
      <section className="card">
        <p className="muted">
          {t('settings.hager.loading')}
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
          <h2>{t('settings.hager.title')}</h2>

          <p className="muted">
            {t('settings.hager.intro')}
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
            <span>{t('settings.hager.username')}</span>
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

          <div className="form-field settings-password-field">
            <span id="hager-password-label">
              {t('settings.hager.password')}
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
                ? t('settings.hager.passwordStored')
                : t('settings.hager.passwordMissing')}
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

              {t('settings.hager.clearPassword')}
            </label>
          </div>

          <label className="form-field">
            <span>{t('settings.hager.installationId')}</span>
            <input
              type="text"
              inputMode="numeric"
              value={installationId}
              maxLength={50}
              placeholder={t('settings.hager.examplePrefix', { value: '1000123456' })}
              onChange={(event) => {
                setInstallationId(event.target.value)
              }}
            />
          </label>

          <label className="form-field">
            <span>{t('settings.hager.serialNumber')}</span>
            <input
              type="text"
              inputMode="numeric"
              value={serialNumber}
              maxLength={50}
              placeholder={t('settings.hager.examplePrefix', { value: '300012345678' })}
              onChange={(event) => {
                setSerialNumber(event.target.value)
              }}
            />
          </label>
        </div>

        <p className="muted">
          {t('settings.hager.idHint')} flow.hager.com/e-mobility/
          <strong>{t('settings.hager.installationId')}</strong>/<strong>{t('settings.hager.serialNumber')}</strong>/…
        </p>
      </section>

      <section className="settings-section">
        <div>
          <h2>{t('settings.importRules.title')}</h2>

          <p className="muted">
            {t('settings.importRules.intro')}
          </p>
        </div>

        <label className="settings-checkbox-control">
          <input
            type="checkbox"
            checked={skipEmptySessions}
            onChange={(event) => {
              setSkipEmptySessions(event.target.checked)
            }}
          />
          {t('settings.importRules.skipEmpty')}
        </label>
      </section>

      <section className="settings-section">
        <div>
          <h2>{t('settings.autoImport.title')}</h2>

          <p className="muted">
            {t('settings.autoImport.intro')}
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
          {t('settings.autoImport.enable')}
        </label>

        {!savedComplete && (
          <small className="muted">
            {t('settings.autoImport.credentialsFirst')}
          </small>
        )}

        <div className="form-grid settings-business-grid">
          <label className="form-field">
            <span>{t('settings.autoImport.everyHours')}</span>
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
            <span>{t('settings.autoImport.startingAt')}</span>
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

      </section>

      <div className="settings-actions">
        <button
          className="button button-primary"
          type="submit"
          disabled={isSaving || isTesting}
        >
          {isSaving
            ? t('settings.hager.saving')
            : t('settings.hager.save')}
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
              : t('settings.autoImport.credentialsFirst')
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

export default AdminHagerSettingsForm
