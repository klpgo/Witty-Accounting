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

interface InvoiceCancellationFinalizeFormProps {
  cancellationId: number
  onFinalized: (invoice: Invoice) => void
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
      'Soll die Stornorechnung verbindlich finalisiert werden?',
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
          : 'Die Stornorechnung konnte nicht finalisiert werden.',
      )

      try {
        const refreshedInvoice =
          await getInvoice(
            accessToken,
            cancellationId,
          )

        onFinalized(refreshedInvoice)
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
        Storno abschließen
      </p>

      <h2>Stornorechnung finalisieren</h2>

      <p className="muted finalize-intro">
        Nach der Finalisierung wird die
        Stornorechnung unveränderlich und als PDF
        archiviert.
      </p>

      <form
        className="finalize-form"
        onSubmit={handleSubmit}
      >
        <label className="form-field">
          <span>Stornodatum</span>

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
              ? 'Stornorechnung wird finalisiert …'
              : 'Stornorechnung verbindlich finalisieren'}
          </button>
        </div>
      </form>
    </section>
  )
}

export default InvoiceCancellationFinalizeForm
