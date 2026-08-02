import {
  type FormEvent,
  useState,
} from 'react'
import {
  Link,
  useNavigate,
  useSearchParams,
} from 'react-router-dom'

import { confirmPasswordReset } from '../api/auth'
import PasswordFields from '../components/PasswordFields'
import { useAppSettings } from '../settings/useAppSettings'


function ResetPasswordPage() {
  const { appName } = useAppSettings()
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const token = searchParams.get('token') ?? ''

  const [newPassword, setNewPassword] =
    useState('')
  const [confirmPassword, setConfirmPassword] =
    useState('')
  const [isSubmitting, setIsSubmitting] =
    useState(false)
  const [errorMessage, setErrorMessage] =
    useState<string | null>(null)

  async function handleSubmit(
    event: FormEvent<HTMLFormElement>,
  ): Promise<void> {
    event.preventDefault()

    if (newPassword !== confirmPassword) {
      setErrorMessage(
        'Die beiden Passwörter stimmen nicht überein.',
      )

      return
    }

    setIsSubmitting(true)
    setErrorMessage(null)

    try {
      await confirmPasswordReset(
        token,
        newPassword,
      )

      navigate('/login?passwordReset=success', {
        replace: true,
      })
    } catch (error) {
      setErrorMessage(
        error instanceof Error
          ? error.message
          : 'Das Passwort konnte nicht gespeichert werden.',
      )
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <main className="page page-centered">
      <section className="card login-card">
        <p className="eyebrow">{appName}</p>

        <h1>Neues Passwort</h1>

        {token ? (
          <>
            <p className="login-intro">
              Lege jetzt dein neues persönliches
              Passwort fest.
            </p>

            <form
              className="login-form"
              onSubmit={handleSubmit}
            >
              <PasswordFields
                newPassword={newPassword}
                confirmPassword={confirmPassword}
                onNewPasswordChange={setNewPassword}
                onConfirmPasswordChange={
                  setConfirmPassword
                }
              />

              {errorMessage && (
                <p className="form-error" role="alert">
                  {errorMessage}
                </p>
              )}

              <button
                className="button button-primary"
                type="submit"
                disabled={isSubmitting}
              >
                {isSubmitting
                  ? 'Passwort wird gespeichert …'
                  : 'Passwort speichern'}
              </button>
            </form>
          </>
        ) : (
          <>
            <p className="form-error" role="alert">
              Der Reset-Link enthält kein gültiges Token.
            </p>

            <p className="login-link-row">
              <Link to="/forgot-password">
                Neuen Reset-Link anfordern
              </Link>
            </p>
          </>
        )}
      </section>
    </main>
  )
}


export default ResetPasswordPage
