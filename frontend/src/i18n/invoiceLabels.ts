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
