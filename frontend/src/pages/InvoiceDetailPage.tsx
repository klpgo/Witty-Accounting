import {
  useEffect,
  useState,
} from 'react'
import {
  Link,
  useNavigate,
  useParams,
} from 'react-router-dom'

import {
  archiveInvoicePdf,
  downloadInvoicePdf,
  getInvoice,
  InvoiceApiError,
  deleteInvoiceDraft,
  exportInvoiceSftp,
  sendInvoiceEmail,
  type Invoice,
} from '../api/invoices'
import { getAccessToken } from '../auth/tokenStorage'
import { useAuth } from '../auth/useAuth'
import InvoiceFinalizeForm from '../components/InvoiceFinalizeForm'
import InvoiceCancellationCreateForm from '../components/InvoiceCancellationCreateForm'
import InvoiceCancellationFinalizeForm from '../components/InvoiceCancellationFinalizeForm'

import {
  getUser,
  UserApiError,
  type User,
} from '../api/users'
import {
  formatDate,
  formatLocalDateTime,
  formatServicePeriod,
  formatUtcDateTime,
} from '../utils/dateFormat'
import {
  formatCurrency,
  formatNumber,
} from '../utils/numberFormat'
import {
  documentTypeLabel,
  invoiceStatusLabel,
} from '../i18n/invoiceLabels'
import { useTranslation } from '../i18n/useTranslation'


function InvoiceDetailPage() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const { invoiceId } = useParams()
  const { user, signOut } = useAuth()
  const isAdmin = user?.is_admin === true

  const numericInvoiceId = Number(invoiceId)

  const [invoice, setInvoice] =
    useState<Invoice | null>(null)

  const [recipient, setRecipient] =
    useState<User | null>(null)

  const [isLoading, setIsLoading] =
    useState(true)

  const [
    errorMessage,
    setErrorMessage,
  ] = useState<string | null>(null)

  const [
    pdfErrorMessage,
    setPdfErrorMessage,
  ] = useState<string | null>(null)

  const [
    pdfSuccessMessage,
    setPdfSuccessMessage,
  ] = useState<string | null>(null)

  const [isArchiving, setIsArchiving] =
    useState(false)

  const [isDeleting, setIsDeleting] =
    useState(false)

  const [
    deleteErrorMessage,
    setDeleteErrorMessage,
  ] = useState<string | null>(null)

  const [
    isDownloading,
    setIsDownloading,
  ] = useState(false)

  const [isPrinting, setIsPrinting] =
    useState(false)

  const [
    isSendingEmail,
    setIsSendingEmail,
  ] = useState(false)

  const [
    emailErrorMessage,
    setEmailErrorMessage,
  ] = useState<string | null>(null)

  const [
    emailSuccessMessage,
    setEmailSuccessMessage,
  ] = useState<string | null>(null)

  const [isExporting, setIsExporting] =
    useState(false)

  const [
    exportErrorMessage,
    setExportErrorMessage,
  ] = useState<string | null>(null)

  const [
    exportSuccessMessage,
    setExportSuccessMessage,
  ] = useState<string | null>(null)

  useEffect(() => {
    if (
      !Number.isInteger(numericInvoiceId) ||
      numericInvoiceId <= 0
    ) {
      setErrorMessage(
        t('invoiceDetail.invalidId'),
      )
      setIsLoading(false)
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

    const token = accessToken
    const controller = new AbortController()

    async function loadInvoice(): Promise<void> {
      try {
        const loadedInvoice = await getInvoice(
          token,
          numericInvoiceId,
          controller.signal,
        )
        setInvoice(loadedInvoice)

        if (isAdmin) {
          const loadedRecipient = await getUser(
            token,
            loadedInvoice.user_id,
            controller.signal,
          )

          setRecipient(loadedRecipient)
        } else {
          setRecipient(null)
        }
      } catch (error) {
        if (
          error instanceof Error &&
          error.name === 'AbortError'
        ) {
          return
        }

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
            : t('invoiceDetail.loadFailed'),
        )
      } finally {
        if (!controller.signal.aborted) {
          setIsLoading(false)
        }
      }
    }

    void loadInvoice()

    return () => {
      controller.abort()
    }
  }, [
    isAdmin,
    navigate,
    numericInvoiceId,
    signOut,
  ])

  async function handlePdfDownload(): Promise<void> {
    if (invoice === null) {
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

    setPdfErrorMessage(null)
    setIsDownloading(true)

    try {
      const pdfBlob = await downloadInvoicePdf(
        accessToken,
        invoice.id,
      )

      const baseName =
        invoice.invoice_number ??
        `rechnung-${invoice.id}`

      const fileName =
        `${baseName}.pdf`.replace(
          /[^a-zA-Z0-9._-]/g,
          '-',
        )

      const downloadUrl =
        URL.createObjectURL(pdfBlob)

      const anchor =
        document.createElement('a')

      anchor.href = downloadUrl
      anchor.download = fileName

      document.body.append(anchor)
      anchor.click()
      anchor.remove()

      URL.revokeObjectURL(downloadUrl)
    } catch (error) {
        if (
          (
            error instanceof InvoiceApiError ||
            error instanceof UserApiError
          ) &&
          error.status === 401
        ) {
        signOut()

        navigate('/login', {
          replace: true,
        })

        return
      }

      setPdfErrorMessage(
        error instanceof Error
          ? error.message
          : t('invoiceDetail.pdf.loadFailed'),
      )
    } finally {
      setIsDownloading(false)
    }
  }

  function handleFinalized(
    finalizedInvoice: Invoice,
    warning?: string,
  ): void {
    setInvoice(finalizedInvoice)
    setPdfSuccessMessage(null)
    setPdfErrorMessage(warning ?? null)
  }

  async function handleArchivePdf(): Promise<void> {
    if (invoice === null) {
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

    setPdfErrorMessage(null)
    setPdfSuccessMessage(null)
    setIsArchiving(true)

    try {
      setInvoice(
        await archiveInvoicePdf(
          accessToken,
          invoice.id,
        ),
      )
      setPdfSuccessMessage(
        t('invoiceDetail.pdf.generated'),
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

      setPdfErrorMessage(
        error instanceof Error
          ? error.message
          : t('invoiceDetail.pdf.generateFailed'),
      )
    } finally {
      setIsArchiving(false)
    }
  }

  async function handleEmailSend(): Promise<void> {
    if (
      !isAdmin ||
      invoice === null ||
      invoice.status !== 'finalized' ||
      invoice.pdf_storage_path === null ||
      recipient === null ||
      recipient.invoice_delivery_post
    ) {
      return
    }

    const isCancellation =
      invoice.document_type === 'cancellation'

    const documentNumber =
      invoice.invoice_number ??
      `#${invoice.id}`

    const isPortalNotification =
      !recipient.invoice_delivery_email &&
      !recipient.invoice_delivery_post

    const confirmKey = isPortalNotification
      ? isCancellation
        ? 'invoiceDetail.email.confirmPortalCancellation'
        : 'invoiceDetail.email.confirmPortalInvoice'
      : isCancellation
        ? 'invoiceDetail.email.confirmCancellation'
        : 'invoiceDetail.email.confirmInvoice'

    const confirmed = window.confirm(
      t(confirmKey, { number: documentNumber }) +
        '\n\n' +
        t('invoiceDetail.email.recipient') +
        '\n' +
        `${invoice.recipient_name}\n` +
        recipient.email,
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

    setEmailErrorMessage(null)
    setEmailSuccessMessage(null)
    setIsSendingEmail(true)

    try {
      const result = await sendInvoiceEmail(
        accessToken,
        invoice.id,
      )

      setEmailSuccessMessage(
        t(
          isPortalNotification
            ? 'invoiceDetail.email.sentPortal'
            : isCancellation
              ? 'invoiceDetail.email.sentCancellation'
              : 'invoiceDetail.email.sentInvoice',
          { email: result.recipient_email },
        ),
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

      setEmailErrorMessage(
        error instanceof Error
          ? error.message
          : t('invoiceDetail.email.failed'),
      )
    } finally {
      setIsSendingEmail(false)
    }
  }

  async function handlePdfPrint(): Promise<void> {
    if (
      !isAdmin ||
      invoice === null ||
      invoice.status !== 'finalized' ||
      invoice.pdf_storage_path === null ||
      recipient === null ||
      recipient.invoice_delivery_email ||
      !recipient.invoice_delivery_post
    ) {
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

    setPdfErrorMessage(null)
    setIsPrinting(true)

    try {
      const pdfBlob = await downloadInvoicePdf(
        accessToken,
        invoice.id,
      )

      const printUrl = URL.createObjectURL(pdfBlob)
      const printFrame = document.createElement(
        'iframe',
      )

      printFrame.title = t('invoiceDetail.print.frameTitle')
      printFrame.style.position = 'fixed'
      printFrame.style.right = '0'
      printFrame.style.bottom = '0'
      printFrame.style.width = '1px'
      printFrame.style.height = '1px'
      printFrame.style.border = '0'
      printFrame.style.opacity = '0'
      printFrame.style.pointerEvents = 'none'

      await new Promise<void>((resolve, reject) => {
        const loadTimeout = window.setTimeout(() => {
          printFrame.remove()
          URL.revokeObjectURL(printUrl)
          reject(
            new Error(
              t('invoiceDetail.print.openFailed'),
            ),
          )
        }, 15_000)

        printFrame.addEventListener(
          'load',
          () => {
            window.clearTimeout(loadTimeout)

            window.setTimeout(() => {
              try {
                const printWindow =
                  printFrame.contentWindow

                if (printWindow === null) {
                  throw new Error(
                    t('invoiceDetail.print.windowFailed'),
                  )
                }

                printWindow.focus()
                printWindow.print()
                resolve()
              } catch (error) {
                printFrame.remove()
                URL.revokeObjectURL(printUrl)
                reject(error)
              }
            }, 250)
          },
          { once: true },
        )

        printFrame.src = printUrl
        document.body.append(printFrame)
      })

      window.setTimeout(() => {
        printFrame.remove()
        URL.revokeObjectURL(printUrl)
      }, 60_000)
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

      setPdfErrorMessage(
        error instanceof Error
          ? error.message
          : t('invoiceDetail.print.failed'),
      )
    } finally {
      setIsPrinting(false)
    }
  }

  async function handleSftpExport(): Promise<void> {
    if (
      !isAdmin ||
      invoice === null ||
      invoice.status !== 'finalized' ||
      invoice.pdf_storage_path === null
    ) {
      return
    }

    const documentNumber =
      invoice.invoice_number ?? `#${invoice.id}`
    const confirmed = window.confirm(
      `PDF ${documentNumber} per SFTP exportieren?`,
    )

    if (!confirmed) {
      return
    }

    const accessToken = getAccessToken()

    if (accessToken === null) {
      signOut()
      navigate('/login', { replace: true })
      return
    }

    setIsExporting(true)
    setExportErrorMessage(null)
    setExportSuccessMessage(null)

    try {
      const result = await exportInvoiceSftp(
        accessToken,
        invoice.id,
      )

      setInvoice((currentInvoice) =>
        currentInvoice === null
          ? null
          : {
              ...currentInvoice,
              pdf_exported_at: result.exported_at,
              pdf_export_remote_path:
                result.remote_path,
            },
      )
      setExportSuccessMessage(
        t('invoiceDetail.exported', { path: result.remote_path }),
      )
    } catch (error) {
      if (
        error instanceof InvoiceApiError &&
        error.status === 401
      ) {
        signOut()
        navigate('/login', { replace: true })
        return
      }

      setExportErrorMessage(
        error instanceof Error
          ? error.message
          : t('invoiceDetail.exportFailed'),
      )
    } finally {
      setIsExporting(false)
    }
  }

  async function handleDeleteDraft(): Promise<void> {
    if (
      !isAdmin ||
      invoice === null ||
      invoice.status !== 'draft'
    ) {
      return
    }

    const confirmed = window.confirm(
      t(
        invoice.document_type === 'cancellation'
          ? 'invoiceDetail.deleteConfirmCancellation'
          : 'invoiceDetail.deleteConfirmInvoice',
      ),
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

    setDeleteErrorMessage(null)
    setIsDeleting(true)

    try {
      await deleteInvoiceDraft(
        accessToken,
        invoice.id,
      )

      navigate('/invoices', {
        replace: true,
      })
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

      setDeleteErrorMessage(
        error instanceof Error
          ? error.message
          : t('invoiceDetail.deleteFailed'),
      )
    } finally {
      setIsDeleting(false)
    }
  }

  if (isLoading) {
    return (
      <div className="page">
        <section className="card">
          <p className="muted">
            {t('invoiceDetail.loading')}
          </p>
        </section>
      </div>
    )
  }

  if (
    errorMessage !== null ||
    invoice === null
  ) {
    return (
      <div className="page">
        <Link
          className="back-link"
          to="/invoices"
        >
          {t('invoiceDetail.back')}
        </Link>

        <section
          className="card form-error"
          role="alert"
        >
          {errorMessage ??
            t('invoiceDetail.notFound')}
        </section>
      </div>
    )
  }

  const hasArchivedPdf =
    invoice.pdf_storage_path !== null

  const isPostalDeliveryOnly =
    isAdmin &&
    recipient?.invoice_delivery_post === true &&
    recipient.invoice_delivery_email === false

  const canSendInvoiceEmail =
    isAdmin &&
    recipient !== null &&
    recipient.invoice_delivery_post === false

  const isPortalDelivery =
    canSendInvoiceEmail &&
    recipient.invoice_delivery_email === false

  return (
    <div className="page invoice-detail-page">
      <div className="detail-header-actions">
        <Link
          className="back-link"
          to="/invoices"
        >
          {t('invoiceDetail.back')}
        </Link>

        {isAdmin && invoice.status === 'draft' && (
          <button
            className="button button-danger"
            type="button"
            disabled={isDeleting}
            onClick={() => {
              void handleDeleteDraft()
            }}
          >
            {isDeleting
              ? t('invoiceDetail.deleting')
              : t('invoiceDetail.delete')}
          </button>
        )}

        {canSendInvoiceEmail &&
          invoice.status === 'finalized' &&
          (
          <button
            className="button button-secondary"
            type="button"
            disabled={
              !hasArchivedPdf ||
              isSendingEmail
            }
            onClick={() => {
              void handleEmailSend()
            }}
          >
            {isSendingEmail
              ? t('invoiceDetail.email.sending')
              : isPortalDelivery
                ? t('invoiceDetail.email.sendPortal')
                : t('invoiceDetail.email.send')}
          </button>
        )}

        {isPostalDeliveryOnly &&
          invoice.status === 'finalized' && (
          <button
            className="button button-secondary"
            type="button"
            disabled={
              !hasArchivedPdf ||
              isPrinting
            }
            onClick={() => {
              void handlePdfPrint()
            }}
          >
            {isPrinting
              ? t('invoiceDetail.printing')
              : t('invoiceDetail.print')}
          </button>
        )}

        {isAdmin &&
          invoice.status === 'finalized' && (
          <button
            className="button button-secondary"
            type="button"
            disabled={
              !hasArchivedPdf ||
              isExporting
            }
            onClick={() => {
              void handleSftpExport()
            }}
          >
            {isExporting
              ? t('invoiceDetail.exporting')
              : t('invoiceDetail.export')}
          </button>
        )}

        {isAdmin &&
          invoice.status === 'finalized' &&
          !hasArchivedPdf && (
          <button
            className="button button-primary"
            type="button"
            disabled={isArchiving}
            onClick={() => {
              void handleArchivePdf()
            }}
          >
            {isArchiving
              ? t('invoiceDetail.pdf.generating')
              : t('invoiceDetail.pdf.generate')}
          </button>
        )}

        <button
          className="button button-primary"
          type="button"
          disabled={
            !hasArchivedPdf ||
            isDownloading
          }
          onClick={() => {
            void handlePdfDownload()
          }}
        >
          {isDownloading
            ? t('invoiceDetail.pdf.downloading')
            : t('invoiceDetail.pdf.download')}
        </button>
      </div>

      <header className="page-header">
        <div>
          <p className="eyebrow">
            {documentTypeLabel(
              t,
              invoice.document_type,
            )}
          </p>

          <h1>
            {invoice.invoice_number ??
              t('common.draftNumber', { id: invoice.id })}
          </h1>

          <p className="muted">
            {t('invoiceDetail.recipientLine', { name: invoice.recipient_name })}
          </p>
        </div>

        <span
          className={
            invoice.status === 'finalized'
              ? 'status-badge status-finalized'
              : 'status-badge status-draft'
          }
        >
          {invoiceStatusLabel(t, invoice.status)}
        </span>
      </header>

      {deleteErrorMessage && (
        <section
          className="form-error detail-error"
          role="alert"
        >
          {deleteErrorMessage}
        </section>
      )}

      {isAdmin &&
        invoice.status === 'finalized' &&
        !hasArchivedPdf &&
        !pdfErrorMessage && (
        <section
          className="form-error detail-error"
          role="status"
        >
          {t('invoiceDetail.pdf.missingHint')}
        </section>
      )}

      {pdfErrorMessage && (
        <section
          className="form-error detail-error"
          role="alert"
        >
          {pdfErrorMessage}
        </section>
      )}

      {pdfSuccessMessage && (
        <section
          className="form-success detail-error"
          role="status"
        >
          {pdfSuccessMessage}
        </section>
      )}

      {emailErrorMessage && (
        <section
          className="form-error detail-error"
          role="alert"
        >
          {emailErrorMessage}
        </section>
      )}

      {emailSuccessMessage && (
        <section
          className="form-success detail-error"
          role="status"
        >
          {emailSuccessMessage}
        </section>
      )}

      {exportErrorMessage && (
        <section
          className="form-error detail-error"
          role="alert"
        >
          {exportErrorMessage}
        </section>
      )}

      {exportSuccessMessage && (
        <section
          className="form-success detail-error"
          role="status"
        >
          {exportSuccessMessage}
        </section>
      )}

      <section className="invoice-summary-grid">
        <article className="card">
          <p className="eyebrow">
            {t('invoiceDetail.data.eyebrow')}
          </p>

          <dl className="detail-list">
            <div>
              <dt>{t('invoiceDetail.data.issueDate')}</dt>
              <dd>
                {formatDate(
                  invoice.issue_date,
                )}
              </dd>
            </div>

            <div>
              <dt>{t('invoiceDetail.data.dueDate')}</dt>
              <dd>
                {formatDate(
                  invoice.due_date,
                )}
              </dd>
            </div>

            <div>
              <dt>{t('invoiceDetail.data.servicePeriod')}</dt>
              <dd>
                {formatServicePeriod(
                  invoice.service_period_start,
                  invoice.service_period_end,
                )}
              </dd>
            </div>

            <div>
              <dt>{t('invoiceDetail.data.created')}</dt>
              <dd>
                {formatUtcDateTime(
                  invoice.created_at,
                )}
              </dd>
            </div>

            {isAdmin &&
              invoice.pdf_exported_at !== null && (
              <div>
                <dt>{t('invoiceDetail.data.lastExport')}</dt>
                <dd>
                  {formatUtcDateTime(
                    invoice.pdf_exported_at,
                  )}
                  {invoice.pdf_export_remote_path && (
                    <>
                      <br />
                      <span className="muted">
                        {invoice.pdf_export_remote_path}
                      </span>
                    </>
                  )}
                </dd>
              </div>
            )}
          </dl>
        </article>

        <article className="card">
          <p className="eyebrow">
            {t('invoiceDetail.recipient.eyebrow')}
          </p>

          <h2>{invoice.recipient_name}</h2>

          <p className="invoice-address">
            {invoice.recipient_address}
          </p>
        </article>

        <article className="card summary-card">
          <p className="eyebrow">
            {t('invoiceDetail.totals.eyebrow')}
          </p>

          <dl className="detail-list">
            <div>
              <dt>{t('invoiceDetail.totals.net')}</dt>
              <dd>
                {formatCurrency(
                  invoice.total_net,
                  invoice.currency,
                )}
              </dd>
            </div>

            <div>
              <dt>{t('invoiceDetail.totals.vat')}</dt>
              <dd>
                {formatCurrency(
                  invoice.vat_amount,
                  invoice.currency,
                )}
              </dd>
            </div>

            <div className="invoice-total-row">
              <dt>{t('invoiceDetail.totals.total')}</dt>
              <dd>
                {formatCurrency(
                  invoice.total_gross,
                  invoice.currency,
                )}
              </dd>
            </div>
          </dl>
        </article>
      </section>

      {isAdmin &&
        invoice.status === 'draft' &&
        invoice.document_type === 'invoice' && (
          <InvoiceFinalizeForm
            invoiceId={invoice.id}
            onFinalized={handleFinalized}
          />
      )}

      {isAdmin &&
        invoice.status === 'draft' &&
        invoice.document_type ===
          'cancellation' && (
          <InvoiceCancellationFinalizeForm
            cancellationId={invoice.id}
            onFinalized={handleFinalized}
          />
      )}

      {invoice.document_type ===
        'cancellation' && (
        <section className="card detail-section">
          <p className="eyebrow">
            {t('invoiceDetail.cancellation.eyebrow')}
          </p>

          <dl className="detail-list">
            <div>
              <dt>{t('invoiceDetail.cancellation.original')}</dt>
              <dd>
                {invoice.original_invoice_id
                  ? `#${invoice.original_invoice_id}`
                  : '–'}
              </dd>
            </div>

            <div>
              <dt>{t('invoiceDetail.cancellation.reason')}</dt>
              <dd>
                {invoice.cancellation_reason ??
                  '–'}
              </dd>
            </div>
          </dl>
        </section>
      )}

      <section className="card table-card detail-section">
        <div className="section-heading">
          <div>
            <p className="eyebrow">
              {t('invoiceDetail.items.eyebrow')}
            </p>

            <h2>
              {t('invoiceDetail.items.count', {
                count: invoice.items.length,
              })}
            </h2>
          </div>
        </div>

        <div className="table-scroll">
          <table className="data-table invoice-items-table">
            <thead>
              <tr>
                <th>{t('invoiceDetail.items.position')}</th>
                <th className="invoice-item-description">
                  {t('invoiceDetail.items.description')}
                </th>
                <th>{t('invoiceDetail.items.period')}</th>
                <th>{t('invoiceDetail.items.station')}</th>
                <th className="table-number">
                  {t('invoiceDetail.items.energy')}
                </th>
                <th className="table-number">
                  {t('invoiceDetail.items.net')}
                </th>
                <th className="table-number">
                  {t('invoiceDetail.items.vat')}
                </th>
                <th className="table-number">
                  {t('invoiceDetail.items.gross')}
                </th>
              </tr>
            </thead>

            <tbody>
              {invoice.items.map((item) => (
                <tr key={item.id}>
                  <td>
                    {item.position_number}
                  </td>

                  <td className="invoice-item-description">
                    <strong>
                      {item.description}
                    </strong>
                  </td>

                  <td>
                    {item.item_type ===
                    'charging_session' ? (
                      <>
                        {formatLocalDateTime(
                          item.session_start,
                        )}
                        <br />
                        <span className="muted">
                          {t('common.until')}{' '}
                          {formatLocalDateTime(
                            item.session_end,
                          )}
                        </span>
                      </>
                    ) : (
                      '–'
                    )}
                  </td>

                  <td>{item.station_id ?? '–'}</td>

                  <td className="table-number">
                    {item.energy_total_kwh === null
                      ? '–'
                      : `${formatNumber(
                          item.energy_total_kwh,
                        )} kWh`}
                  </td>

                  <td className="table-number">
                    {formatCurrency(
                      item.net_amount,
                      invoice.currency,
                    )}
                  </td>

                  <td className="table-number">
                    {formatCurrency(
                      item.vat_amount,
                      invoice.currency,
                    )}
                  </td>

                  <td className="table-number">
                    <strong>
                      {formatCurrency(
                        item.gross_amount,
                        invoice.currency,
                      )}
                    </strong>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
      {isAdmin &&
        invoice.status === 'finalized' &&
        invoice.document_type === 'invoice' &&
        invoice.cancelled_at === null && (
          <InvoiceCancellationCreateForm
            invoiceId={invoice.id}
          />
      )}
    </div>
  )
}

export default InvoiceDetailPage
