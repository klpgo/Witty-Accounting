import {
  type FormEvent,
  useState,
} from 'react'
import { Link } from 'react-router-dom'

import { requestPasswordReset } from '../api/auth'
import { useAppSettings } from '../settings/useAppSettings'
import { useTranslation } from '../i18n/useTranslation'
import SystemMessage from '../components/SystemMessage'


function ForgotPasswordPage() {
  const { t } = useTranslation()
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
          : t('forgotPassword.failed'),
      )
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <main className="page page-centered">
      <section className="card login-card">
        <p className="eyebrow">{tenantName}</p>

        <h1>{t('forgotPassword.title')}</h1>

        <p className="login-intro">
          {t('forgotPassword.intro')}
        </p>

        <form
          className="login-form"
          onSubmit={handleSubmit}
        >
          <label className="form-field">
            <span>{t('common.email')}</span>

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

          <SystemMessage
        kind="error"
        message={errorMessage}
        onClose={() => {
          setErrorMessage(null)
        }}
      />

          <SystemMessage
        kind="success"
        message={successMessage}
        onClose={() => {
          setSuccessMessage(null)
        }}
      />

          <button
            className="button button-primary"
            type="submit"
            disabled={isSubmitting}
          >
            {isSubmitting
              ? t('forgotPassword.submitting')
              : t('forgotPassword.submit')}
          </button>

          <p className="login-link-row">
            <Link to="/login">
              {t('common.backToLogin')}
            </Link>
          </p>
        </form>
      </section>
    </main>
  )
}


export default ForgotPasswordPage
