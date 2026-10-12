import { useState } from 'react'
import { useNavigate } from 'react-router-dom'

import {
  InvoiceApiError,
  requestInvoiceInquiry,
  type Invoice,
} from '../api/invoices'
import { localizeMessage } from '../api/errors'
import { getAccessToken } from '../auth/tokenStorage'
import { useAuth } from '../auth/useAuth'
import { useTranslation } from '../i18n/useTranslation'
import { formatDate, formatUtcDateTime } from '../utils/dateFormat'
import SystemMessage from './SystemMessage'

interface InvoiceReviewPanelProps {
  invoice: Invoice
  isAdmin: boolean
  onChanged: (invoice: Invoice) => void
}

/*
 * Hinweise zur automatischen Abrechnung auf der Detailseite.
 *
 * Kunden: Entwurf zur Prüfung mit Button "Nachfrage zum Rechnungsentwurf";
 * danach die Bitte, sich per E-Mail an den Rechnungssteller zu wenden.
 * Administratoren: Prüfstatus, Nachfrage, Fehler und Zustellung.
 */
function InvoiceReviewPanel({
  invoice,
  isAdmin,
  onChanged,
}: InvoiceReviewPanelProps) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const { signOut } = useAuth()

  const [isSending, setIsSending] = useState(false)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)

  if (invoice.review_status === null) {
    return null
  }

  const isDraft = invoice.status === 'draft'

  async function handleInquiry(): Promise<void> {
    if (!window.confirm(t('invoiceReview.inquiryConfirm'))) {
      return
    }

    const accessToken = getAccessToken()

    if (accessToken === null) {
      signOut()
      navigate('/login', { replace: true })
      return
    }

    setErrorMessage(null)
    setIsSending(true)

    try {
      const result = await requestInvoiceInquiry(accessToken, invoice.id)

      onChanged({
        ...result.invoice,
        review_contact_email:
          result.contact_email ?? result.invoice.review_contact_email,
      })
    } catch (error) {
      if (error instanceof InvoiceApiError && error.status === 401) {
        signOut()
        navigate('/login', { replace: true })
        return
      }

      setErrorMessage(
        error instanceof Error
          ? error.message
          : t('invoiceReview.inquiryFailed'),
      )
    } finally {
      setIsSending(false)
    }
  }

  if (isAdmin) {
    let text: string | null = null
    let isProblem = false

    if (isDraft && invoice.review_status === 'in_review') {
      text = t('invoiceReview.admin.inReview', {
        date: formatDate(invoice.review_due_date),
      })

      if (invoice.review_notified_at === null) {
        text += ' ' + t('invoiceReview.admin.notNotified')
        isProblem = true
      }
    } else if (isDraft && invoice.review_status === 'on_hold') {
      text = t('invoiceReview.admin.onHold', {
        date: formatUtcDateTime(invoice.inquiry_at),
      })
      isProblem = true
    } else if (isDraft && invoice.review_status === 'failed') {
      text = t('invoiceReview.admin.failed')
      isProblem = true
    } else if (!isDraft && invoice.delivery_status !== null) {
      switch (invoice.delivery_status) {
        case 'sent':
          text = t('invoiceReview.admin.deliverySent')
          break
        case 'postal':
          text = t('invoiceReview.admin.deliveryPostal')
          isProblem = true
          break
        case 'failed':
          text = t('invoiceReview.admin.deliveryFailed')
          isProblem = true
          break
        default:
          text = t('invoiceReview.admin.deliveryPending')
      }
    }

    if (text === null) {
      return null
    }

    return (
      <section
        className={
          isProblem
            ? 'card detail-section review-panel review-panel-attention'
            : 'card detail-section review-panel'
        }
      >
        <p className="eyebrow">{t('invoiceReview.admin.eyebrow')}</p>
        <p>{text}</p>
        {invoice.notification_error && (
          <p className="muted">
            {t('invoiceReview.admin.error', {
              message: localizeMessage(
                invoice.notification_error,
                invoice.notification_error_code,
              ) ?? '',
            })}
          </p>
        )}
      </section>
    )
  }

  if (!isDraft) {
    return null
  }

  const contactEmail = invoice.review_contact_email
  const mailtoHref =
    contactEmail === null
      ? null
      : `mailto:${contactEmail}?subject=${encodeURIComponent(
          t('invoiceReview.mailSubject', { id: invoice.id }),
        )}`

  return (
    <section
      className={
        invoice.review_status === 'in_review'
          ? 'card detail-section review-panel'
          : 'card detail-section review-panel review-panel-attention'
      }
    >
      <p className="eyebrow">{t('invoiceReview.eyebrow')}</p>

      {invoice.review_status === 'in_review' && (
        <>
          <p>
            {t('invoiceReview.inReview', {
              date: formatDate(invoice.review_due_date),
            })}
          </p>

          <SystemMessage
        kind="error"
        message={errorMessage}
        onClose={() => {
          setErrorMessage(null)
        }}
      />

          <div className="form-actions">
            <button
              className="button button-secondary"
              type="button"
              disabled={isSending}
              onClick={() => {
                void handleInquiry()
              }}
            >
              {isSending
                ? t('invoiceReview.inquirySending')
                : t('invoiceReview.inquiryButton')}
            </button>
          </div>
        </>
      )}

      {invoice.review_status === 'on_hold' && (
        <>
          <p role="status">
            {contactEmail === null
              ? t('invoiceReview.onHoldNoEmail')
              : t('invoiceReview.onHold', { email: contactEmail })}
          </p>

          {mailtoHref !== null && (
            <div className="form-actions">
              <a className="button button-primary" href={mailtoHref}>
                {t('invoiceReview.writeEmail')}
              </a>
            </div>
          )}
        </>
      )}

      {invoice.review_status === 'failed' && (
        <p>{t('invoiceReview.failedCustomer')}</p>
      )}
    </section>
  )
}

export default InvoiceReviewPanel
