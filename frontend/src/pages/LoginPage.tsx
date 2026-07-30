import {
  type FormEvent,
  useState,
} from 'react'
import {
  Navigate,
  useNavigate,
} from 'react-router-dom'

import { useAuth } from '../auth/useAuth'
import { useAppSettings } from '../settings/useAppSettings'

function LoginPage() {
  const { appName } = useAppSettings()
  const navigate = useNavigate()
  const {
    signIn,
    status,
  } = useAuth()

  const [email, setEmail] = useState('')
  const [password, setPassword] =
    useState('')

  const [
    errorMessage,
    setErrorMessage,
  ] = useState<string | null>(null)

  const [
    isSubmitting,
    setIsSubmitting,
  ] = useState(false)

  if (status === 'authenticated') {
    return (
      <Navigate
        to="/"
        replace
      />
    )
  }

  if (status === 'loading') {
    return (
      <main className="page page-centered">
        <section className="card loading-card">
          <p className="eyebrow">
            {appName}
          </p>

          <h1>Sitzung wird geprüft</h1>

          <p className="muted">
            Bitte einen Augenblick …
          </p>
        </section>
      </main>
    )
  }

  async function handleSubmit(
    event: FormEvent<HTMLFormElement>,
  ): Promise<void> {
    event.preventDefault()

    setErrorMessage(null)
    setIsSubmitting(true)

    try {
      await signIn(
        email,
        password,
      )

      navigate('/', {
        replace: true,
      })
    } catch (error) {
      setErrorMessage(
        error instanceof Error
          ? error.message
          : 'Die Anmeldung ist fehlgeschlagen.',
      )
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <main className="page page-centered">
      <section className="card login-card">
        <p className="eyebrow">
          {appName}
        </p>

        <h1>Anmeldung</h1>

        <p className="login-intro">
           Bitte melde dich mit deiner E-Mail-Adresse
          und deinem Passwort an.
        </p>

        <form
          className="login-form"
          onSubmit={handleSubmit}
        >
          <label className="form-field">
            <span>E-Mail-Adresse</span>

            <input
              type="email"
              autoComplete="username"
              value={email}
              onChange={(event) => {
                setEmail(event.target.value)
              }}
              required
            />
          </label>

          <label className="form-field">
            <span>Passwort</span>

            <input
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(event) => {
                setPassword(event.target.value)
              }}
              required
            />
          </label>

          {errorMessage && (
            <p
              className="form-error"
              role="alert"
            >
              {errorMessage}
            </p>
          )}

          <button
            className="button button-primary"
            type="submit"
            disabled={isSubmitting}
          >
            {isSubmitting
              ? 'Anmeldung läuft …'
              : 'Anmelden'}
          </button>
        </form>
      </section>
    </main>
  )
}

export default LoginPage
