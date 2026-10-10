import type { I18nContextValue } from './i18nContext'

type Translate = I18nContextValue['t']

/** Status einer Rechnung (Entwurf, finalisiert) */
export function invoiceStatusLabel(t: Translate, status: string): string {
  switch (status) {
    case 'draft':
      return t('invoice.status.draft')
    case 'finalized':
      return t('invoice.status.finalized')
    default:
      return status
  }
}

/** Belegart; `short` für Tabellen ("Storno" statt "Stornorechnung") */
export function documentTypeLabel(
  t: Translate,
  documentType: string,
  short = false,
): string {
  switch (documentType) {
    case 'invoice':
      return t('invoice.type.invoice')
    case 'cancellation':
      return short
        ? t('invoice.type.cancellationShort')
        : t('invoice.type.cancellation')
    default:
      return documentType
  }
}

/** Prüfstatus eines Entwurfs der automatischen Abrechnung */
export function reviewStatusLabel(t: Translate, reviewStatus: string): string {
  switch (reviewStatus) {
    case 'in_review':
      return t('invoice.review.in_review')
    case 'on_hold':
      return t('invoice.review.on_hold')
    case 'failed':
      return t('invoice.review.failed')
    default:
      return reviewStatus
  }
}

/** Badge (Text und CSS-Klasse) für Rechnungslisten und Detailseite */
export function invoiceBadge(
  t: Translate,
  invoice: { status: string; review_status: string | null },
): { label: string; className: string } {
  if (invoice.status === 'draft' && invoice.review_status !== null) {
    return {
      label: reviewStatusLabel(t, invoice.review_status),
      className:
        invoice.review_status === 'in_review'
          ? 'status-badge status-review'
          : 'status-badge status-hold',
    }
  }

  return {
    label: invoiceStatusLabel(t, invoice.status),
    className:
      invoice.status === 'finalized'
        ? 'status-badge status-finalized'
        : 'status-badge status-draft',
  }
}
