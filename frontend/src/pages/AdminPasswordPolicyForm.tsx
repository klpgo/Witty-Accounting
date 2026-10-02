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

function AdminPasswordPolicyForm() {
  const { t } = useTranslation()
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
  const [
    frontendBaseUrl,
    setFrontendBaseUrl,
  ] = useState('')
  const [
    passwordResetTokenExpireMinutes,
    setPasswordResetTokenExpireMinutes,
  ] = useState('60')

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
        setFrontendBaseUrl(
          loadedSettings.frontend_base_url,
        )
        setPasswordResetTokenExpireMinutes(
          String(
            loadedSettings
              .password_reset_token_expire_minutes,
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
            : t('settings.password.loadFailed'),
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

    const minLength = Number(
      passwordMinLength,
    )
    const normalizedFrontendBaseUrl =
      frontendBaseUrl.trim().replace(/\/+$/, '')
    const resetTokenExpireMinutes = Number(
      passwordResetTokenExpireMinutes,
    )

    setErrorMessage(null)
    setSuccessMessage(null)

    if (
      !Number.isInteger(minLength) ||
      minLength < 8 ||
      minLength > 128
    ) {
      setErrorMessage(
        t('settings.password.minLengthRange'),
      )
      return
    }

    let parsedFrontendBaseUrl: URL

    try {
      parsedFrontendBaseUrl = new URL(
        normalizedFrontendBaseUrl,
      )
    } catch {
      setErrorMessage(
        t('settings.password.urlInvalid'),
      )
      return
    }

    if (
      !['http:', 'https:'].includes(
        parsedFrontendBaseUrl.protocol,
      ) ||
      parsedFrontendBaseUrl.username !== '' ||
      parsedFrontendBaseUrl.password !== '' ||
      parsedFrontendBaseUrl.search !== '' ||
      parsedFrontendBaseUrl.hash !== ''
    ) {
      setErrorMessage(
        t('settings.password.urlInvalidDetail'),
      )
      return
    }

    if (
      !Number.isInteger(resetTokenExpireMinutes) ||
      resetTokenExpireMinutes < 1 ||
      resetTokenExpireMinutes > 10080
    ) {
      setErrorMessage(
        t('settings.password.expiryRange'),
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
            frontend_base_url:
              normalizedFrontendBaseUrl,
            password_reset_token_expire_minutes:
              resetTokenExpireMinutes,
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
      setFrontendBaseUrl(
        updatedSettings.frontend_base_url,
      )
      setPasswordResetTokenExpireMinutes(
        String(
          updatedSettings
            .password_reset_token_expire_minutes,
        ),
      )

      setSuccessMessage(
        t('settings.password.saved'),
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
          : t('settings.password.saveFailed'),
      )
    } finally {
      setIsSaving(false)
    }
  }

  if (isLoading) {
    return (
      <section className="card">
        <p className="muted">
          {t('settings.password.loading')}
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
          <h2>{t('settings.password.title')}</h2>

          <p className="muted">
            {t('settings.password.intro')}
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
            <span>{t('settings.password.minLength')}</span>

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
              {t('settings.password.minLengthHint')}
            </small>
          </label>

          <label className="form-field settings-checkbox-field">
            <span>{t('settings.password.uppercase')}</span>

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

              {t('settings.password.uppercaseHint')}
            </span>
          </label>

          <label className="form-field settings-checkbox-field">
            <span>{t('settings.password.lowercase')}</span>

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

              {t('settings.password.lowercaseHint')}
            </span>
          </label>

          <label className="form-field settings-checkbox-field">
            <span>{t('settings.password.digits')}</span>

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

              {t('settings.password.digitsHint')}
            </span>
          </label>

          <label className="form-field settings-checkbox-field">
            <span>{t('settings.password.special')}</span>

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

              {t('settings.password.specialHint')}
            </span>
          </label>
        </div>
      </section>

      <section className="settings-section">
        <div>
          <h2>{t('settings.password.reset.title')}</h2>

          <p className="muted">
            {t('settings.password.reset.intro')}
          </p>
        </div>

        <div className="form-grid settings-business-grid">
          <label className="form-field settings-wide-field">
            <span>{t('settings.password.reset.url')}</span>

            <input
              type="url"
              value={frontendBaseUrl}
              maxLength={2048}
              placeholder={t('settings.password.reset.urlPlaceholder')}
              autoCapitalize="none"
              autoCorrect="off"
              spellCheck={false}
              onChange={(event) => {
                setFrontendBaseUrl(
                  event.target.value,
                )
              }}
              required
            />

            <small className="muted">
              {t('settings.password.reset.urlHint')}
            </small>
          </label>

          <label className="form-field">
            <span>{t('settings.password.reset.expiry')}</span>

            <input
              type="number"
              min="1"
              max="10080"
              step="1"
              value={passwordResetTokenExpireMinutes}
              onChange={(event) => {
                setPasswordResetTokenExpireMinutes(
                  event.target.value,
                )
              }}
              required
            />

            <small className="muted">
              {t('settings.password.reset.expiryHint')}
            </small>
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
            ? t('settings.password.saving')
            : t('settings.password.save')}
        </button>
      </div>
    </form>
  )
}

export default AdminPasswordPolicyForm
