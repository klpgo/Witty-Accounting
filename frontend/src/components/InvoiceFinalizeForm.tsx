import {
  type FormEvent,
  useState,
} from 'react'
import { useNavigate } from 'react-router-dom'

import {
  finalizeInvoice,
  getInvoice,
  InvoiceApiError,
  type Invoice,
} from '../api/invoices'
import { getAccessToken } from '../auth/tokenStorage'
import { useAuth } from '../auth/useAuth'

interface InvoiceFinalizeFormProps {
  invoiceId: number
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

function getDefaultIssueDate(): string {
  return formatDateInput(new Date())
}

function getDefaultDueDate(): string {
  const dueDate = new Date()

  dueDate.setDate(
    dueDate.getDate() + 14,
  )

  return formatDateInput(dueDate)
}

function InvoiceFinalizeForm({
  invoiceId,
  onFinalized,
}: InvoiceFinalizeFormProps) {
  const navigate = useNavigate()
  const { signOut } = useAuth()

  const [issueDate, setIssueDate] =
    useState(getDefaultIssueDate)

  const [dueDate, setDueDate] =
    useState(getDefaultDueDate)

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

    if (dueDate < issueDate) {
      setErrorMessage(
        'Das Fälligkeitsdatum darf nicht vor dem Rechnungsdatum liegen.',
      )
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
      const finalizedInvoice =
        await finalizeInvoice(
          accessToken,
          invoiceId,
          {
            issue_date: issueDate,
            due_date: dueDate,
          },
        )

      onFinalized(finalizedInvoice)
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
          : 'Die Rechnung konnte nicht finalisiert werden.',
      )

      /*
       * Die Finalisierung kann bereits erfolgreich
       * gewesen sein, obwohl die anschließende
       * PDF-Archivierung fehlgeschlagen ist.
       */
      try {
        const refreshedInvoice =
          await getInvoice(
            accessToken,
            invoiceId,
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
        Entwurf abschließen
      </p>

      <h2>Rechnung finalisieren</h2>

      <p className="muted finalize-intro">
        Nach der Finalisierung sind die
        Rechnungsdaten unveränderlich. Das PDF
        wird automatisch erstellt und archiviert.
      </p>

      <form
        className="finalize-form"
        onSubmit={handleSubmit}
      >
        <div className="form-grid">
          <label className="form-field">
            <span>Rechnungsdatum</span>

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

          <label className="form-field">
            <span>Fälligkeitsdatum</span>

            <input
              type="date"
              value={dueDate}
              min={issueDate}
              onChange={(event) => {
                setDueDate(
                  event.target.value,
                )
              }}
              disabled={isSubmitting}
              required
            />
          </label>
        </div>

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
              ? 'Rechnung wird finalisiert …'
              : 'Rechnung verbindlich finalisieren'}
          </button>
        </div>
      </form>
    </section>
  )
}

export default InvoiceFinalizeForm
