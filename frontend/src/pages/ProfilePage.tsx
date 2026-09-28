import {
  type FormEvent,
  useCallback,
  useEffect,
  useState,
} from 'react'
import { useNavigate } from 'react-router-dom'

import {
  getOwnProfile,
  updateOwnProfile,
  changeOwnPassword,
  getInvoiceDeliveryFlags,
  getInvoiceDeliveryMethod,
  UserApiError,
  type InvoiceDeliveryMethod,
} from '../api/users'
import { getAccessToken } from '../auth/tokenStorage'
import { useAuth } from '../auth/useAuth'
import PasswordFields from '../components/PasswordFields'
import { useTranslation } from '../i18n/useTranslation'
import { useAppSettings } from '../settings/useAppSettings'

function ProfilePage() {
  const { t } = useTranslation()
  const { defaultLanguage } = useAppSettings()
  const navigate = useNavigate()
  const {
    signOut,
    updateAuthenticatedUser,
  } = useAuth()

  const [email, setEmail] = useState('')
  const [firstName, setFirstName] =
    useState('')
  const [lastName, setLastName] =
    useState('')
  const [address, setAddress] =
    useState('')
  const [phone, setPhone] =
    useState('')
  // '' = Standardsprache des Mandanten
  const [language, setLanguage] =
    useState('')

  const [invoiceDeliveryMethod, setInvoiceDeliveryMethod] =
    useState<InvoiceDeliveryMethod>('email')

  const [isLoading, setIsLoading] =
    useState(true)
  const [isSaving, setIsSaving] =
    useState(false)
  const [
    currentPassword,
    setCurrentPassword,
  ] = useState('')
  const [
    newPassword,
    setNewPassword,
  ] = useState('')
  const [
    confirmPassword,
    setConfirmPassword,
  ] = useState('')

  const [
    isChangingPassword,
    setIsChangingPassword,
  ] = useState(false)

  const [
    passwordErrorMessage,
    setPasswordErrorMessage,
  ] = useState<string | null>(null)
  const [
    passwordSuccessMessage,
    setPasswordSuccessMessage,
  ] = useState<string | null>(null)

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

    async function loadProfile(): Promise<void> {
      const accessToken = getAccessToken()

      if (accessToken === null) {
        handleUnauthorized()
        return
      }

      setIsLoading(true)
      setErrorMessage(null)

      try {
        const profile = await getOwnProfile(
          accessToken,
          controller.signal,
        )

        setEmail(profile.email)
        setFirstName(profile.first_name)
        setLastName(profile.last_name)
        setAddress(profile.address ?? '')
        setPhone(profile.phone ?? '')
        setLanguage(profile.language ?? '')
        setInvoiceDeliveryMethod(
          getInvoiceDeliveryMethod(profile),
        )
      } catch (error) {
        if (
          error instanceof DOMException &&
          error.name === 'AbortError'
        ) {
          return
        }

        if (
          error instanceof UserApiError &&
          error.status === 401
        ) {
          handleUnauthorized()
          return
        }

        setErrorMessage(
          error instanceof Error
            ? error.message
            : t('profile.loadFailed'),
        )
      } finally {
        if (!controller.signal.aborted) {
          setIsLoading(false)
        }
      }
    }

    void loadProfile()

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
      const updatedProfile =
        await updateOwnProfile(
          accessToken,
          {
            email,
            first_name: firstName,
            last_name: lastName,
            address:
              address.trim() || null,
            phone:
              phone.trim() || null,
            language: language || null,
            ...getInvoiceDeliveryFlags(
              invoiceDeliveryMethod,
            ),
          },
        )

      setEmail(updatedProfile.email)
      setFirstName(
        updatedProfile.first_name,
      )
      setLastName(
        updatedProfile.last_name,
      )
      setAddress(
        updatedProfile.address ?? '',
      )
      setPhone(
        updatedProfile.phone ?? '',
      )
      setLanguage(updatedProfile.language ?? '')
      setInvoiceDeliveryMethod(
        getInvoiceDeliveryMethod(updatedProfile),
      )

      updateAuthenticatedUser(
        updatedProfile,
      )

      setSuccessMessage(
        t('profile.saved'),
      )
    } catch (error) {
      if (
        error instanceof UserApiError &&
        error.status === 401
      ) {
        handleUnauthorized()
        return
      }

      setErrorMessage(
        error instanceof Error
          ? error.message
          : t('profile.saveFailed'),
      )
    } finally {
      setIsSaving(false)
    }
  }

  async function handlePasswordChange(
    event: FormEvent<HTMLFormElement>,
  ): Promise<void> {
    event.preventDefault()

    if (newPassword !== confirmPassword) {
      setPasswordErrorMessage(
        t('profile.password.mismatch'),
      )
      setPasswordSuccessMessage(null)
      return
    }

    const accessToken = getAccessToken()

    if (accessToken === null) {
      handleUnauthorized()
      return
    }

    setIsChangingPassword(true)
    setPasswordErrorMessage(null)
    setPasswordSuccessMessage(null)

    try {
      await changeOwnPassword(
        accessToken,
        currentPassword,
        newPassword,
      )

      setCurrentPassword('')
      setNewPassword('')
      setConfirmPassword('')

      setPasswordSuccessMessage(
        t('profile.password.changed'),
      )
    } catch (error) {
      if (
        error instanceof UserApiError &&
        error.status === 401
      ) {
        handleUnauthorized()
        return
      }

      setPasswordErrorMessage(
        error instanceof Error
          ? error.message
          : t('profile.password.failed'),
      )
    } finally {
      setIsChangingPassword(false)
    }
  }

  return (
    <div className="page">
      <header className="page-header">
        <div>
          <p className="eyebrow">
            {t('profile.eyebrow')}
          </p>

          <h1>{t('profile.title')}</h1>

          <p className="muted">
            {t('profile.intro')}
          </p>
        </div>
      </header>

      {isLoading ? (
        <section className="card">
          <p className="muted">
            {t('profile.loading')}
          </p>
        </section>
      ) : (
        <>
          <form
            className="card admin-form"
            onSubmit={handleSubmit}
          >
            <div>
              <h2>{t('profile.personal.title')}</h2>

              <p className="muted">
                {t('profile.personal.intro')}
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

            <div className="form-grid">
              <label className="form-field">
                {t('profile.firstName')}
                <input
                  type="text"
                  value={firstName}
                  required
                  maxLength={100}
                  autoComplete="given-name"
                  onChange={(event) =>
                    setFirstName(
                      event.target.value,
                    )
                  }
                />
              </label>

              <label className="form-field">
                {t('profile.lastName')}
                <input
                  type="text"
                  value={lastName}
                  required
                  maxLength={100}
                  autoComplete="family-name"
                  onChange={(event) =>
                    setLastName(
                      event.target.value,
                    )
                  }
                />
              </label>

              <label className="form-field">
                {t('common.email')}
                <input
                  type="email"
                  value={email}
                  required
                  maxLength={255}
                  autoComplete="email"
                  onChange={(event) =>
                    setEmail(
                      event.target.value,
                    )
                  }
                />
              </label>

              <label className="form-field">
                {t('profile.phone')}
                <input
                  type="tel"
                  value={phone}
                  maxLength={50}
                  autoComplete="tel"
                  onChange={(event) =>
                    setPhone(
                      event.target.value,
                    )
                  }
                />
              </label>
            </div>

            <label className="form-field">
              {t('profile.address')}
              <textarea
                value={address}
                rows={4}
                maxLength={500}
                autoComplete="street-address"
                onChange={(event) =>
                  setAddress(
                    event.target.value,
                  )
                }
              />
            </label>

            <label className="form-field">
              {t('common.language')}
              <select
                value={language}
                onChange={(event) =>
                  setLanguage(event.target.value)
                }
              >
                <option value="">
                  {t('common.language.systemDefault', {
                    language: t(
                      defaultLanguage === 'en'
                        ? 'language.en'
                        : 'language.de',
                    ),
                  })}
                </option>
                <option value="de">{t('language.de')}</option>
                <option value="en">{t('language.en')}</option>
              </select>
              <small className="muted">
                {t('profile.language.hint')}
              </small>
            </label>

            <div>
              <h2>{t('profile.delivery.title')}</h2>

              <p className="muted">
                {t('profile.delivery.intro')}
              </p>
            </div>

            <div className="checkbox-group">
              <label className="checkbox-field">
                <input
                  type="radio"
                  name="invoice-delivery-method"
                  value="email"
                  checked={invoiceDeliveryMethod === 'email'}
                  onChange={() =>
                    setInvoiceDeliveryMethod('email')
                  }
                />

                {t('profile.delivery.email')}
              </label>

              <label className="checkbox-field">
                <input
                  type="radio"
                  name="invoice-delivery-method"
                  value="post"
                  checked={invoiceDeliveryMethod === 'post'}
                  onChange={() =>
                    setInvoiceDeliveryMethod('post')
                  }
                />

                {t('profile.delivery.post')}
              </label>

              <label className="checkbox-field">
                <input
                  type="radio"
                  name="invoice-delivery-method"
                  value="portal"
                  checked={invoiceDeliveryMethod === 'portal'}
                  onChange={() =>
                    setInvoiceDeliveryMethod('portal')
                  }
                />

                {t('profile.delivery.portal')}
              </label>
            </div>

            <div className="form-actions">
              <button
                className="button button-primary"
                type="submit"
                disabled={isSaving}
              >
                {isSaving
                  ? t('profile.saving')
                  : t('profile.save')}
              </button>
            </div>
          </form>

          <form
            className="card admin-form"
            onSubmit={handlePasswordChange}
          >
            <div>
              <h2>{t('profile.password.title')}</h2>

              <p className="muted">
                {t('profile.password.intro')}
              </p>
            </div>

            {passwordErrorMessage && (
              <div
                className="form-error"
                role="alert"
              >
                {passwordErrorMessage}
              </div>
            )}

            {passwordSuccessMessage && (
              <div
                className="form-success"
                role="status"
              >
                {passwordSuccessMessage}
              </div>
            )}

            <label className="form-field">
              {t('profile.password.current')}
              <input
                type="password"
                value={currentPassword}
                required
                maxLength={1024}
                autoComplete="current-password"
                onChange={(event) =>
                  setCurrentPassword(
                    event.target.value,
                  )
                }
              />
            </label>

            <PasswordFields
              newPassword={newPassword}
              confirmPassword={confirmPassword}
              onNewPasswordChange={setNewPassword}
              onConfirmPasswordChange={
                setConfirmPassword
              }
            />

            <div className="form-actions">
              <button
                className="button button-primary"
                type="submit"
                disabled={isChangingPassword}
              >
                {isChangingPassword
                  ? t('profile.password.submitting')
                  : t('profile.password.submit')}
              </button>
            </div>
          </form>
        </>
      )}
    </div>
  )
}

export default ProfilePage
