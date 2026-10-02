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
import { useTranslation } from '../i18n/useTranslation'


function ResetPasswordPage() {
  const { t } = useTranslation()
  const { tenantName } = useAppSettings()
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
        t('resetPassword.mismatch'),
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
          : t('resetPassword.failed'),
      )
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <main className="page page-centered">
      <section className="card login-card">
        <p className="eyebrow">{tenantName}</p>

        <h1>{t('resetPassword.title')}</h1>

        {token ? (
          <>
            <p className="login-intro">
              {t('resetPassword.intro')}
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
                  ? t('resetPassword.submitting')
                  : t('resetPassword.submit')}
              </button>
            </form>
          </>
        ) : (
          <>
            <p className="form-error" role="alert">
              {t('resetPassword.invalidToken')}
            </p>

            <p className="login-link-row">
              <Link to="/forgot-password">
                {t('resetPassword.requestNewLink')}
              </Link>
            </p>
          </>
        )}
      </section>
    </main>
  )
}


export default ResetPasswordPage
