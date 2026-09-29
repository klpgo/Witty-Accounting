import {
  type FormEvent,
  useCallback,
  useEffect,
  useState,
} from 'react'
import { useNavigate } from 'react-router-dom'

import {
  getGlobalSettings,
  SettingsApiError,
  updateGlobalSettings,
} from '../api/settings'
import { getAccessToken } from '../auth/tokenStorage'
import { useAuth } from '../auth/useAuth'
import { useTranslation } from '../i18n/useTranslation'

function AdminAccessSettingsForm() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const { signOut } = useAuth()

  const [
    maintenanceMode,
    setMaintenanceMode,
  ] = useState(false)

  const [dashboardNote, setDashboardNote] =
    useState('')

  const [isLoading, setIsLoading] =
    useState(true)
  const [isSaving, setIsSaving] =
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
          await getGlobalSettings(
            accessToken,
            controller.signal,
          )

        setMaintenanceMode(
          loadedSettings.maintenance_mode,
        )
        setDashboardNote(
          loadedSettings.dashboard_note ?? '',
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
            : t('settings.access.loadFailed'),
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

    const accessToken = getAccessToken()

    if (accessToken === null) {
      handleUnauthorized()
      return
    }

    setIsSaving(true)
    setErrorMessage(null)
    setSuccessMessage(null)

    try {
      const updatedSettings =
        await updateGlobalSettings(
          accessToken,
          {
            maintenance_mode:
              maintenanceMode,
            dashboard_note:
              dashboardNote.trim() || null,
          },
        )

      setMaintenanceMode(
        updatedSettings.maintenance_mode,
      )
      setDashboardNote(
        updatedSettings.dashboard_note ?? '',
      )

      setSuccessMessage(
        t('settings.access.saved'),
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
          : t('settings.access.saveFailed'),
      )
    } finally {
      setIsSaving(false)
    }
  }

  if (isLoading) {
    return (
      <section className="card">
        <p className="muted">
          {t('settings.access.loading')}
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
          <h2>{t('settings.access.title')}</h2>

          <p className="muted">
            {t('settings.access.intro')}
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

        <label className="form-field settings-checkbox-field">
          <span>{t('settings.access.maintenance')}</span>

          <span className="settings-checkbox-control">
            <input
              type="checkbox"
              checked={maintenanceMode}
              onChange={(event) => {
                setMaintenanceMode(
                  event.target.checked,
                )
              }}
            />

            {t('settings.access.maintenanceHint')}
          </span>
        </label>

        <label className="form-field">
          {t('settings.access.note')}
          <textarea
            value={dashboardNote}
            maxLength={4000}
            rows={6}
            placeholder={t('settings.access.notePlaceholder')}
            onChange={(event) => {
              setDashboardNote(
                event.target.value,
              )
            }}
          />

          <span className="form-hint">
            {t('settings.access.noteHint')}
          </span>
        </label>
      </section>

      <div className="settings-actions">
        <button
          className="button button-primary"
          type="submit"
          disabled={isSaving}
        >
          {isSaving
            ? t('settings.access.saving')
            : t('settings.access.save')}
        </button>
      </div>
    </form>
  )
}

export default AdminAccessSettingsForm
