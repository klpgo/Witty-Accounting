import {
  type FormEvent,
  useState,
} from 'react'
import { Link } from 'react-router-dom'

import { requestPasswordReset } from '../api/auth'
import { useAppSettings } from '../settings/useAppSettings'


function ForgotPasswordPage() {
  const { tenantName } = useAppSettings()
  const [email, setEmail] = useState('')
  const [isSubmitting, setIsSubmitting] =
    useState(false)
  const [errorMessage, setErrorMessage] =
    useState<string | null>(null)
  const [successMessage, setSuccessMessage] =
    useState<string | null>(null)

  async function handleSubmit(
    event: FormEvent<HTMLFormElement>,
  ): Promise<void> {
    event.preventDefault()

    setIsSubmitting(true)
    setErrorMessage(null)
    setSuccessMessage(null)

    try {
      setSuccessMessage(
        await requestPasswordReset(email),
      )
    } catch (error) {
      setErrorMessage(
        error instanceof Error
          ? error.message
          : 'Die Anfrage konnte nicht verarbeitet werden.',
      )
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <main className="page page-centered">
      <section className="card login-card">
        <p className="eyebrow">{tenantName}</p>

        <h1>Passwort vergessen</h1>

        <p className="login-intro">
          Gib deine E-Mail-Adresse ein. Wir senden dir
          einen einmaligen Link zum Festlegen eines neuen
          Passworts.
        </p>

        <form
          className="login-form"
          onSubmit={handleSubmit}
        >
          <label className="form-field">
            <span>E-Mail-Adresse</span>

            <input
              type="email"
              autoComplete="email"
              value={email}
              onChange={(event) =>
                setEmail(event.target.value)
              }
              required
              maxLength={255}
            />
          </label>

          {errorMessage && (
            <p className="form-error" role="alert">
              {errorMessage}
            </p>
          )}

          {successMessage && (
            <p className="form-success" role="status">
              {successMessage}
            </p>
          )}

          <button
            className="button button-primary"
            type="submit"
            disabled={isSubmitting}
          >
            {isSubmitting
              ? 'E-Mail wird angefordert …'
              : 'Reset-Link anfordern'}
          </button>

          <p className="login-link-row">
            <Link to="/login">
              Zurück zur Anmeldung
            </Link>
          </p>
        </form>
      </section>
    </main>
  )
}


export default ForgotPasswordPage
