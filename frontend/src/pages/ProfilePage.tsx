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
  UserApiError,
} from '../api/users'
import { getAccessToken } from '../auth/tokenStorage'
import { useAuth } from '../auth/useAuth'
import PasswordFields from '../components/PasswordFields'

function ProfilePage() {
  const navigate = useNavigate()
  const {
    signOut,
    updateAuthenticatedUser,
  } = useAuth()

  const [email, setEmail] = useState('')
  const [salutation, setSalutation] =
    useState('')
  const [firstName, setFirstName] =
    useState('')
  const [lastName, setLastName] =
    useState('')
  const [address, setAddress] =
    useState('')
  const [phone, setPhone] =
    useState('')

  const [
    invoiceDeliveryEmail,
    setInvoiceDeliveryEmail,
  ] = useState(false)
  const [
    invoiceDeliveryPost,
    setInvoiceDeliveryPost,
  ] = useState(false)

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
        setSalutation(
          profile.salutation ?? '',
        )
        setFirstName(profile.first_name)
        setLastName(profile.last_name)
        setAddress(profile.address ?? '')
        setPhone(profile.phone ?? '')
        setInvoiceDeliveryEmail(
          profile.invoice_delivery_email,
        )
        setInvoiceDeliveryPost(
          profile.invoice_delivery_post,
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
            : 'Die Profildaten konnten nicht geladen werden.',
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
            salutation:
              salutation.trim() || null,
            first_name: firstName,
            last_name: lastName,
            address:
              address.trim() || null,
            phone:
              phone.trim() || null,
            invoice_delivery_email:
              invoiceDeliveryEmail,
            invoice_delivery_post:
              invoiceDeliveryPost,
          },
        )

      setEmail(updatedProfile.email)
      setSalutation(
        updatedProfile.salutation ?? '',
      )
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
      setInvoiceDeliveryEmail(
        updatedProfile.invoice_delivery_email,
      )
      setInvoiceDeliveryPost(
        updatedProfile.invoice_delivery_post,
      )

      updateAuthenticatedUser(
        updatedProfile,
      )

      setSuccessMessage(
        'Die persönlichen Daten wurden gespeichert.',
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
          : 'Die persönlichen Daten konnten nicht gespeichert werden.',
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
        'Die beiden neuen Passwörter stimmen nicht überein.',
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
        'Das Passwort wurde geändert.',
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
          : 'Das Passwort konnte nicht geändert werden.',
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
            Benutzerkonto
          </p>

          <h1>Meine Daten</h1>

          <p className="muted">
            Persönliche Daten und Einstellungen
            für den Rechnungsversand verwalten.
          </p>
        </div>
      </header>

      {isLoading ? (
        <section className="card">
          <p className="muted">
            Profildaten werden geladen …
          </p>
        </section>
      ) : (
        <>
          <form
            className="card admin-form"
            onSubmit={handleSubmit}
          >
            <div>
              <h2>Persönliche Daten</h2>

              <p className="muted">
                Änderungen gelten ausschließlich
                für das eigene Benutzerkonto.
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
              <label className="form-field profile-salutation-field">
                Anrede
                <input
                  type="text"
                  value={salutation}
                  maxLength={50}
                  autoComplete="honorific-prefix"
                  onChange={(event) =>
                    setSalutation(
                      event.target.value,
                    )
                  }
                />
              </label>

              <label className="form-field">
                Vorname
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
                Nachname
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
                E-Mail-Adresse
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
                Telefonnummer
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
              Anschrift
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

            <div>
              <h2>Rechnungsversand</h2>

              <p className="muted">
                Legen Sie fest, auf welchen Wegen
                Rechnungen zugestellt werden sollen.
              </p>
            </div>

            <div className="form-grid">
              <label className="checkbox-field">
                <input
                  type="checkbox"
                  checked={invoiceDeliveryEmail}
                  onChange={(event) =>
                    setInvoiceDeliveryEmail(
                      event.target.checked,
                    )
                  }
                />

                Rechnung per E-Mail
              </label>

              <label className="checkbox-field">
                <input
                  type="checkbox"
                  checked={invoiceDeliveryPost}
                  onChange={(event) =>
                    setInvoiceDeliveryPost(
                      event.target.checked,
                    )
                  }
                />

                Rechnung per Post
              </label>
            </div>

            <div className="form-actions">
              <button
                className="button button-primary"
                type="submit"
                disabled={isSaving}
              >
                {isSaving
                  ? 'Daten werden gespeichert …'
                  : 'Daten speichern'}
              </button>
            </div>
          </form>

          <form
            className="card admin-form"
            onSubmit={handlePasswordChange}
          >
            <div>
              <h2>Passwort ändern</h2>

              <p className="muted">
                Geben Sie zuerst das aktuelle Passwort
                und anschließend das neue Passwort ein.
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
              Aktuelles Passwort
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
                  ? 'Passwort wird geändert …'
                  : 'Passwort ändern'}
              </button>
            </div>
          </form>
        </>
      )}
    </div>
  )
}

export default ProfilePage
