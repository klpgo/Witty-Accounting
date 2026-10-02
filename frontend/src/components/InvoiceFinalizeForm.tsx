import {
  type FormEvent,
  useEffect,
  useState,
} from 'react'
import { useNavigate } from 'react-router-dom'

import {
  finalizeInvoice,
  getInvoice,
  InvoiceApiError,
  type Invoice,
} from '../api/invoices'
import { getGlobalSettings } from '../api/settings'
import { getAccessToken } from '../auth/tokenStorage'
import { useAuth } from '../auth/useAuth'
import { useTranslation } from '../i18n/useTranslation'

interface InvoiceFinalizeFormProps {
  invoiceId: number
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

function getDefaultIssueDate(): string {
  return formatDateInput(new Date())
}

// Kalendertag JJJJ-MM-TT plus Anzahl Tage
function addDays(day: string, days: number): string {
  const [year, month, date] = day.split('-').map(Number)

  return formatDateInput(new Date(year, month - 1, date + days))
}

function InvoiceFinalizeForm({
  invoiceId,
  onFinalized,
}: InvoiceFinalizeFormProps) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const { signOut } = useAuth()

  const [issueDate, setIssueDate] =
    useState(getDefaultIssueDate)

  // Zahlungsziel aus den Einstellungen (null, solange nicht geladen)
  const [paymentTermDays, setPaymentTermDays] =
    useState<number | null>(null)

  const [dueDate, setDueDate] = useState('')

  // true, sobald das Fälligkeitsdatum von Hand geändert wurde
  const [dueDateChanged, setDueDateChanged] = useState(false)

  useEffect(() => {
    const controller = new AbortController()
    const accessToken = getAccessToken()

    if (accessToken !== null) {
      getGlobalSettings(accessToken, controller.signal)
        .then((settings) => {
          setPaymentTermDays(settings.invoice_payment_term_days)
        })
        .catch(() => {
          // ohne Einstellungen berechnet das Backend das Datum
        })
    }

    return () => {
      controller.abort()
    }
  }, [])

  // Fälligkeitsdatum folgt dem Rechnungsdatum, solange es nicht von Hand
  // geändert wurde
  useEffect(() => {
    if (!dueDateChanged && paymentTermDays !== null && issueDate) {
      setDueDate(addDays(issueDate, paymentTermDays))
    }
  }, [dueDateChanged, issueDate, paymentTermDays])

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

    if (dueDate && dueDate < issueDate) {
      setErrorMessage(
        t('invoiceFinalize.dueBeforeIssue'),
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
            ...(dueDateChanged && dueDate ? { due_date: dueDate } : {}),
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
          : t('invoiceFinalize.failed'),
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
        {t('invoiceFinalize.eyebrow')}
      </p>

      <h2>{t('invoiceFinalize.title')}</h2>

      <p className="muted finalize-intro">
        {t('invoiceFinalize.intro')}
      </p>

      <form
        className="finalize-form"
        onSubmit={handleSubmit}
      >
        <div className="form-grid">
          <label className="form-field">
            <span>{t('invoiceFinalize.issueDate')}</span>

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
            <span>{t('invoiceFinalize.dueDate')}</span>

            <input
              type="date"
              value={dueDate}
              min={issueDate}
              onChange={(event) => {
                setDueDate(
                  event.target.value,
                )
                setDueDateChanged(true)
              }}
              disabled={isSubmitting}
            />
            {paymentTermDays !== null && (
              <small className="muted">
                {t('invoiceFinalize.paymentTermHint', {
                  count: paymentTermDays,
                })}
              </small>
            )}
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
              ? t('invoiceFinalize.submitting')
              : t('invoiceFinalize.submit')}
          </button>
        </div>
      </form>
    </section>
  )
}

export default InvoiceFinalizeForm
