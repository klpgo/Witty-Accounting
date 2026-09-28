import {
  type FormEvent,
  useState,
} from 'react'
import { useNavigate } from 'react-router-dom'

import {
  finalizeInvoiceCancellation,
  getInvoice,
  InvoiceApiError,
  type Invoice,
} from '../api/invoices'
import { getAccessToken } from '../auth/tokenStorage'
import { useAuth } from '../auth/useAuth'
import { useTranslation } from '../i18n/useTranslation'

interface InvoiceCancellationFinalizeFormProps {
  cancellationId: number
  /*
   * warning: Fehlermeldung, wenn die Rechnung finalisiert wurde,
   * das PDF aber nicht archiviert werden konnte. Die Detailseite
   * zeigt sie an, weil dieses Formular danach verschwindet.
   */
  onFinalized: (invoice: Invoice, warning?: string) => void
}

function formatDateInput(date: Date): string {
  const year = date.getFullYear()
  const month = String(
    date.getMonth() + 1,
  ).padStart(2, '0')
  const day = String(
    date.getDate(),
  ).padStart(2, '0')

  return `${year}-${month}-${day}`
}

function InvoiceCancellationFinalizeForm({
  cancellationId,
  onFinalized,
}: InvoiceCancellationFinalizeFormProps) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const { signOut } = useAuth()

  const [issueDate, setIssueDate] =
    useState(() => formatDateInput(new Date()))

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

    const confirmed = window.confirm(
      t('cancellationFinalize.confirm'),
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
        await finalizeInvoiceCancellation(
          accessToken,
          cancellationId,
          {
            issue_date: issueDate,
          },
        )

      onFinalized(cancellation)
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
          : t('cancellationFinalize.failed'),
      )

      try {
        const refreshedInvoice =
          await getInvoice(
            accessToken,
            cancellationId,
          )

        onFinalized(
          refreshedInvoice,
          refreshedInvoice.status === 'finalized' &&
            error instanceof Error
            ? error.message
            : undefined,
        )
      } catch {
        // Die ursprüngliche Fehlermeldung bleibt sichtbar.
      }
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <section className="card detail-section">
      <p className="eyebrow">
        {t('cancellationFinalize.eyebrow')}
      </p>

      <h2>{t('cancellationFinalize.title')}</h2>

      <p className="muted finalize-intro">
        {t('cancellationFinalize.intro')}
      </p>

      <form
        className="finalize-form"
        onSubmit={handleSubmit}
      >
        <label className="form-field">
          <span>{t('cancellationFinalize.date')}</span>

          <input
            type="date"
            value={issueDate}
            onChange={(event) => {
              setIssueDate(
                event.target.value,
              )
            }}
            disabled={isSubmitting}
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
              ? t('cancellationFinalize.submitting')
              : t('cancellationFinalize.submit')}
          </button>
        </div>
      </form>
    </section>
  )
}

export default InvoiceCancellationFinalizeForm
