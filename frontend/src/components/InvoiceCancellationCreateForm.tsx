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

interface InvoiceCancellationCreateFormProps {
  invoiceId: number
}

function InvoiceCancellationCreateForm({
  invoiceId,
}: InvoiceCancellationCreateFormProps) {
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
        'Bitte gib einen Stornogrund an.',
      )
      return
    }

    const confirmed = window.confirm(
      'Soll für diese Rechnung wirklich ein Stornoentwurf erstellt werden?',
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
          : 'Der Stornoentwurf konnte nicht erstellt werden.',
      )
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <section className="card detail-section">
      <p className="eyebrow">
        Rechnung korrigieren
      </p>

      <h2>Rechnung stornieren</h2>

      <p className="muted finalize-intro">
        Es wird zunächst ein Stornoentwurf mit
        negativen Rechnungspositionen erstellt.
        Anschließend muss dieser verbindlich
        finalisiert werden.
      </p>

      <form
        className="finalize-form"
        onSubmit={handleSubmit}
      >
        <label className="form-field">
          <span>Stornogrund</span>

          <textarea
            value={reason}
            maxLength={500}
            rows={4}
            onChange={(event) => {
              setReason(event.target.value)
            }}
            disabled={isSubmitting}
            placeholder="Zum Beispiel: Fehlerhafte Abrechnung"
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
              ? 'Stornoentwurf wird erstellt …'
              : 'Rechnung stornieren'}
          </button>
        </div>
      </form>
    </section>
  )
}

export default InvoiceCancellationCreateForm
