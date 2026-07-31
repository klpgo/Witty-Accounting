import {
  type FormEvent,
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

function AdminPasswordPolicyForm() {
  const navigate = useNavigate()
  const { signOut } = useAuth()

  const [
    passwordMinLength,
    setPasswordMinLength,
  ] = useState('8')
  const [
    passwordRequireUppercase,
    setPasswordRequireUppercase,
  ] = useState(true)
  const [
    passwordRequireLowercase,
    setPasswordRequireLowercase,
  ] = useState(true)
  const [
    passwordRequireDigit,
    setPasswordRequireDigit,
  ] = useState(true)
  const [
    passwordRequireSpecial,
    setPasswordRequireSpecial,
  ] = useState(true)

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

  function handleUnauthorized(): void {
    signOut()

    navigate('/login', {
      replace: true,
    })
  }

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

        setPasswordMinLength(
          String(
            loadedSettings.password_min_length,
          ),
        )
        setPasswordRequireUppercase(
          loadedSettings
            .password_require_uppercase,
        )
        setPasswordRequireLowercase(
          loadedSettings
            .password_require_lowercase,
        )
        setPasswordRequireDigit(
          loadedSettings.password_require_digit,
        )
        setPasswordRequireSpecial(
          loadedSettings
            .password_require_special,
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
            : 'Die Passwortregeln konnten nicht geladen werden.',
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
  }, [navigate, signOut])

  async function handleSubmit(
    event: FormEvent<HTMLFormElement>,
  ): Promise<void> {
    event.preventDefault()

    const minLength = Number(
      passwordMinLength,
    )

    setErrorMessage(null)
    setSuccessMessage(null)

    if (
      !Number.isInteger(minLength) ||
      minLength < 8 ||
      minLength > 128
    ) {
      setErrorMessage(
        'Die Passwort-Mindestlänge muss zwischen 8 und 128 Zeichen liegen.',
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
        await updateGlobalSettings(
          accessToken,
          {
            password_min_length: minLength,
            password_require_uppercase:
              passwordRequireUppercase,
            password_require_lowercase:
              passwordRequireLowercase,
            password_require_digit:
              passwordRequireDigit,
            password_require_special:
              passwordRequireSpecial,
          },
        )

      setPasswordMinLength(
        String(
          updatedSettings.password_min_length,
        ),
      )
      setPasswordRequireUppercase(
        updatedSettings
          .password_require_uppercase,
      )
      setPasswordRequireLowercase(
        updatedSettings
          .password_require_lowercase,
      )
      setPasswordRequireDigit(
        updatedSettings.password_require_digit,
      )
      setPasswordRequireSpecial(
        updatedSettings
          .password_require_special,
      )

      setSuccessMessage(
        'Die Passwortregeln wurden gespeichert.',
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
          : 'Die Passwortregeln konnten nicht gespeichert werden.',
      )
    } finally {
      setIsSaving(false)
    }
  }

  if (isLoading) {
    return (
      <section className="card">
        <p className="muted">
          Passwortregeln werden geladen …
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
          <h2>Passwortregeln</h2>

          <p className="muted">
            Diese Regeln gelten beim neuen Setzen
            oder Ändern eines Passworts. Bestehende
            Passwörter bleiben gültig.
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
            <span>Mindestlänge</span>

            <input
              type="number"
              min="8"
              max="128"
              step="1"
              value={passwordMinLength}
              onChange={(event) => {
                setPasswordMinLength(
                  event.target.value,
                )
              }}
              required
            />

            <small className="muted">
              Mindestens 8, höchstens 128 Zeichen.
            </small>
          </label>

          <label className="form-field settings-checkbox-field">
            <span>Großbuchstaben</span>

            <span className="settings-checkbox-control">
              <input
                type="checkbox"
                checked={passwordRequireUppercase}
                onChange={(event) => {
                  setPasswordRequireUppercase(
                    event.target.checked,
                  )
                }}
              />

              Mindestens einen Großbuchstaben verlangen
            </span>
          </label>

          <label className="form-field settings-checkbox-field">
            <span>Kleinbuchstaben</span>

            <span className="settings-checkbox-control">
              <input
                type="checkbox"
                checked={passwordRequireLowercase}
                onChange={(event) => {
                  setPasswordRequireLowercase(
                    event.target.checked,
                  )
                }}
              />

              Mindestens einen Kleinbuchstaben verlangen
            </span>
          </label>

          <label className="form-field settings-checkbox-field">
            <span>Zahlen</span>

            <span className="settings-checkbox-control">
              <input
                type="checkbox"
                checked={passwordRequireDigit}
                onChange={(event) => {
                  setPasswordRequireDigit(
                    event.target.checked,
                  )
                }}
              />

              Mindestens eine Zahl verlangen
            </span>
          </label>

          <label className="form-field settings-checkbox-field">
            <span>Sonderzeichen</span>

            <span className="settings-checkbox-control">
              <input
                type="checkbox"
                checked={passwordRequireSpecial}
                onChange={(event) => {
                  setPasswordRequireSpecial(
                    event.target.checked,
                  )
                }}
              />

              Mindestens ein Sonderzeichen verlangen
            </span>
          </label>
        </div>
      </section>

      <div className="settings-actions">
        <button
          className="button button-primary"
          type="submit"
          disabled={isSaving}
        >
          {isSaving
            ? 'Passwortregeln werden gespeichert …'
            : 'Passwortregeln speichern'}
        </button>
      </div>
    </form>
  )
}

export default AdminPasswordPolicyForm
