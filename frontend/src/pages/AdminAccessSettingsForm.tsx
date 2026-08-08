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

function AdminAccessSettingsForm() {
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
            : 'Die Zugriffseinstellungen konnten nicht geladen werden.',
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
        'Die Zugriffseinstellungen wurden gespeichert.',
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
          : 'Die Zugriffseinstellungen konnten nicht gespeichert werden.',
      )
    } finally {
      setIsSaving(false)
    }
  }

  if (isLoading) {
    return (
      <section className="card">
        <p className="muted">
          Zugriffseinstellungen werden geladen …
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
          <h2>Dashboard und Zugriff</h2>

          <p className="muted">
            Die Notiz wird allen angemeldeten Benutzern
            auf dem Dashboard angezeigt. Im Wartungsmodus
            können sich nur Administratoren neu anmelden.
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
          <span>Wartungsmodus</span>

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

            Anmeldung nur für Administratoren erlauben
          </span>
        </label>

        <label className="form-field">
          Notiz an die Benutzer
          <textarea
            value={dashboardNote}
            maxLength={4000}
            rows={6}
            placeholder="Zum Beispiel: Die nächste Abrechnung erfolgt am 15. August."
            onChange={(event) => {
              setDashboardNote(
                event.target.value,
              )
            }}
          />

          <span className="form-hint">
            Leer lassen, wenn derzeit keine Mitteilung
            angezeigt werden soll.
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
            ? 'Dashboard wird gespeichert …'
            : 'Dashboard und Zugriff speichern'}
        </button>
      </div>
    </form>
  )
}

export default AdminAccessSettingsForm
