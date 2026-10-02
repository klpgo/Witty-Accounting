import {
  type FormEvent,
  useState,
} from 'react'
import {
  Link,
  Navigate,
  useNavigate,
  useSearchParams,
} from 'react-router-dom'

import { useAuth } from '../auth/useAuth'
import { useAppSettings } from '../settings/useAppSettings'
import { useTranslation } from '../i18n/useTranslation'

function LoginPage() {
  const { t } = useTranslation()
  const { tenantName } = useAppSettings()
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
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
            {tenantName}
          </p>

          <h1>{t('common.sessionCheck.title')}</h1>

          <p className="muted">
            {t('common.sessionCheck.text')}
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
          : t('login.failed'),
      )
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <main className="page page-centered">
      <section className="card login-card">
        <p className="eyebrow">
          {tenantName}
        </p>

        <h1>{t('login.title')}</h1>

        <p className="login-intro">
          {t('login.intro')}
        </p>

        {searchParams.get('passwordReset') ===
          'success' && (
          <p className="form-success" role="status">
            {t('login.passwordResetSuccess')}
          </p>
        )}

        <form
          className="login-form"
          onSubmit={handleSubmit}
        >
          <label className="form-field">
            <span>{t('common.email')}</span>

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
            <span>{t('common.password')}</span>

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

          <p className="login-link-row">
            <Link to="/forgot-password">
              {t('login.forgotPassword')}
            </Link>
          </p>

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
              ? t('login.submitting')
              : t('login.submit')}
          </button>
        </form>
      </section>
    </main>
  )
}

export default LoginPage
