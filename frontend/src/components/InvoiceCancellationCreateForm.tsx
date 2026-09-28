import {
  type FormEvent,
  useState,
} from 'react'
import { useNavigate } from 'react-router-dom'

import {
  createInvoiceCancellation,
  InvoiceApiError,
} from '../api/invoices'
import { getAccessToken } from '../auth/tokenStorage'
import { useAuth } from '../auth/useAuth'
import { useTranslation } from '../i18n/useTranslation'

interface InvoiceCancellationCreateFormProps {
  invoiceId: number
}

function InvoiceCancellationCreateForm({
  invoiceId,
}: InvoiceCancellationCreateFormProps) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const { signOut } = useAuth()

  const [reason, setReason] = useState('')
  const [isSubmitting, setIsSubmitting] =
    useState(false)

  const [
    errorMessage,
    setErrorMessage,
  ] = useState<string | null>(null)

  async function handleSubmit(
    event: FormEvent<HTMLFormElement>,
  ): Promise<void> {
    event.preventDefault()

    const normalizedReason = reason.trim()

    if (!normalizedReason) {
      setErrorMessage(
        t('cancellationCreate.reasonMissing'),
      )
      return
    }

    const confirmed = window.confirm(
      t('cancellationCreate.confirm'),
    )

    if (!confirmed) {
      return
    }

    const accessToken = getAccessToken()

    if (accessToken === null) {
      signOut()

      navigate('/login', {
        replace: true,
      })

      return
    }

    setErrorMessage(null)
    setIsSubmitting(true)

    try {
      const cancellation =
        await createInvoiceCancellation(
          accessToken,
          invoiceId,
          {
            reason: normalizedReason,
          },
        )

      navigate(
        `/invoices/${cancellation.id}`,
      )
    } catch (error) {
      if (
        error instanceof InvoiceApiError &&
        error.status === 401
      ) {
        signOut()

        navigate('/login', {
          replace: true,
        })

        return
      }

      setErrorMessage(
        error instanceof Error
          ? error.message
          : t('cancellationCreate.failed'),
      )
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <section className="card detail-section">
      <p className="eyebrow">
        {t('cancellationCreate.eyebrow')}
      </p>

      <h2>{t('cancellationCreate.title')}</h2>

      <p className="muted finalize-intro">
        {t('cancellationCreate.intro')}
      </p>

      <form
        className="finalize-form"
        onSubmit={handleSubmit}
      >
        <label className="form-field">
          <span>{t('cancellationCreate.reason')}</span>

          <textarea
            value={reason}
            maxLength={500}
            rows={4}
            onChange={(event) => {
              setReason(event.target.value)
            }}
            disabled={isSubmitting}
            placeholder={t('cancellationCreate.reasonPlaceholder')}
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

        <div className="form-actions">
          <button
            className="button button-primary"
            type="submit"
            disabled={isSubmitting}
          >
            {isSubmitting
              ? t('cancellationCreate.submitting')
              : t('cancellationCreate.submit')}
          </button>
        </div>
      </form>
    </section>
  )
}

export default InvoiceCancellationCreateForm
