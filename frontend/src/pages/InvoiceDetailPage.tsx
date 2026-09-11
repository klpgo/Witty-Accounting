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

function formatCurrency(
  value: string | number,
  currency: string,
): string {
  const numericValue = Number(value)

  if (!Number.isFinite(numericValue)) {
    return '–'
  }

  return new Intl.NumberFormat('de-DE', {
    style: 'currency',
    currency,
  }).format(numericValue)
}

function formatNumber(
  value: string | number | null,
  maximumFractionDigits = 3,
): string {
  if (value === null) {
    return '–'
  }

  const numericValue = Number(value)

  if (!Number.isFinite(numericValue)) {
    return '–'
  }

  return new Intl.NumberFormat('de-DE', {
    minimumFractionDigits: 0,
    maximumFractionDigits,
  }).format(numericValue)
}

function formatDate(
  value: string | null,
): string {
  if (value === null) {
    return '–'
  }

  const date = new Date(
    value.length === 10
      ? `${value}T00:00:00`
      : value,
  )

  if (Number.isNaN(date.getTime())) {
    return value
  }

  return new Intl.DateTimeFormat(
    'de-DE',
  ).format(date)
}

function formatDateTime(
  value: string | null,
): string {
  if (value === null) {
    return '–'
  }

  const date = new Date(value)

  if (Number.isNaN(date.getTime())) {
    return value
  }

  return new Intl.DateTimeFormat('de-DE', {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(date)
}

function getStatusLabel(
  status: string,
): string {
  switch (status) {
    case 'draft':
      return 'Entwurf'
    case 'finalized':
      return 'Finalisiert'
    default:
      return status
  }
}

function getDocumentTypeLabel(
  documentType: string,
): string {
  switch (documentType) {
    case 'invoice':
      return 'Rechnung'
    case 'cancellation':
      return 'Stornorechnung'
    default:
      return documentType
  }
}

function InvoiceDetailPage() {
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
        'Die Rechnungs-ID ist ungültig.',
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
            : 'Die Rechnung konnte nicht geladen werden.',
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
          : 'Die PDF konnte nicht geladen werden.',
      )
    } finally {
      setIsDownloading(false)
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

    const documentLabel =
      invoice.document_type === 'cancellation'
        ? 'Stornorechnung'
        : 'Rechnung'

    const documentNumber =
      invoice.invoice_number ??
      `#${invoice.id}`

    const isPortalNotification =
      !recipient.invoice_delivery_email &&
      !recipient.invoice_delivery_post

    const confirmed = window.confirm(
      `${documentLabel} ${documentNumber} ` +
        (isPortalNotification
          ? 'als im Portal verfügbar melden?\n\n'
          : 'per E-Mail versenden?\n\n') +
        'Empfänger:\n' +
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
        isPortalNotification
          ? `Die Download-Benachrichtigung wurde an ` +
            `${result.recipient_email} gesendet.`
          : `Die ${documentLabel} wurde an ` +
            `${result.recipient_email} gesendet.`,
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
          : 'Die Rechnung konnte nicht per E-Mail gesendet werden.',
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

      printFrame.title = 'Rechnung drucken'
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
              'Die PDF konnte nicht zum Drucken geöffnet werden.',
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
                    'Das Druckfenster konnte nicht geöffnet werden.',
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
          : 'Die PDF konnte nicht gedruckt werden.',
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
        `Die PDF wurde nach ${result.remote_path} exportiert.`,
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
          : 'Die PDF konnte nicht per SFTP exportiert werden.',
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

    const documentLabel =
      invoice.document_type === 'cancellation'
        ? 'Stornoentwurf'
        : 'Rechnungsentwurf'

    const confirmed = window.confirm(
      `Soll dieser ${documentLabel} wirklich gelöscht werden?`,
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
          : 'Der Entwurf konnte nicht gelöscht werden.',
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
            Rechnung wird geladen …
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
          ← Zurück zu den Rechnungen
        </Link>

        <section
          className="card form-error"
          role="alert"
        >
          {errorMessage ??
            'Die Rechnung wurde nicht gefunden.'}
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
          ← Zurück zu den Rechnungen
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
              ? 'Entwurf wird gelöscht …'
              : 'Entwurf löschen'}
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
              ? 'E-Mail wird gesendet …'
              : isPortalDelivery
                ? 'Download-Nachricht senden'
                : 'Per E-Mail senden'}
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
              ? 'Druck wird vorbereitet …'
              : 'PDF drucken'}
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
              ? 'PDF wird exportiert …'
              : 'PDF per SFTP exportieren'}
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
            ? 'PDF wird geladen …'
            : 'PDF herunterladen'}
        </button>
      </div>

      <header className="page-header">
        <div>
          <p className="eyebrow">
            {getDocumentTypeLabel(
              invoice.document_type,
            )}
          </p>

          <h1>
            {invoice.invoice_number ??
              `Entwurf #${invoice.id}`}
          </h1>

          <p className="muted">
            Empfänger: {invoice.recipient_name}
          </p>
        </div>

        <span
          className={
            invoice.status === 'finalized'
              ? 'status-badge status-finalized'
              : 'status-badge status-draft'
          }
        >
          {getStatusLabel(invoice.status)}
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

      {pdfErrorMessage && (
        <section
          className="form-error detail-error"
          role="alert"
        >
          {pdfErrorMessage}
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
            Rechnungsdaten
          </p>

          <dl className="detail-list">
            <div>
              <dt>Rechnungsdatum</dt>
              <dd>
                {formatDate(
                  invoice.issue_date,
                )}
              </dd>
            </div>

            <div>
              <dt>Fälligkeitsdatum</dt>
              <dd>
                {formatDate(
                  invoice.due_date,
                )}
              </dd>
            </div>

            <div>
              <dt>Leistungszeitraum</dt>
              <dd>
                {formatDateTime(
                  invoice.service_period_start,
                )}
                {' – '}
                {formatDateTime(
                  invoice.service_period_end,
                )}
              </dd>
            </div>

            <div>
              <dt>Erstellt</dt>
              <dd>
                {formatDateTime(
                  invoice.created_at,
                )}
              </dd>
            </div>

            {isAdmin &&
              invoice.pdf_exported_at !== null && (
              <div>
                <dt>Zuletzt per SFTP exportiert</dt>
                <dd>
                  {formatDateTime(
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
            Rechnungsempfänger
          </p>

          <h2>{invoice.recipient_name}</h2>

          <p className="invoice-address">
            {invoice.recipient_address}
          </p>
        </article>

        <article className="card summary-card">
          <p className="eyebrow">
            Summen
          </p>

          <dl className="detail-list">
            <div>
              <dt>Netto</dt>
              <dd>
                {formatCurrency(
                  invoice.total_net,
                  invoice.currency,
                )}
              </dd>
            </div>

            <div>
              <dt>Umsatzsteuer</dt>
              <dd>
                {formatCurrency(
                  invoice.vat_amount,
                  invoice.currency,
                )}
              </dd>
            </div>

            <div className="invoice-total-row">
              <dt>Gesamt</dt>
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
            onFinalized={setInvoice}
          />
      )}

      {isAdmin &&
        invoice.status === 'draft' &&
        invoice.document_type ===
          'cancellation' && (
          <InvoiceCancellationFinalizeForm
            cancellationId={invoice.id}
            onFinalized={setInvoice}
          />
      )}

      {invoice.document_type ===
        'cancellation' && (
        <section className="card detail-section">
          <p className="eyebrow">
            Stornierung
          </p>

          <dl className="detail-list">
            <div>
              <dt>Originalrechnung</dt>
              <dd>
                {invoice.original_invoice_id
                  ? `#${invoice.original_invoice_id}`
                  : '–'}
              </dd>
            </div>

            <div>
              <dt>Stornogrund</dt>
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
              Positionen
            </p>

            <h2>
              {invoice.items.length}{' '}
              {invoice.items.length === 1
                ? 'Position'
                : 'Positionen'}
            </h2>
          </div>
        </div>

        <div className="table-scroll">
          <table className="data-table">
            <thead>
              <tr>
                <th>Pos.</th>
                <th>Beschreibung</th>
                <th>Zeitraum</th>
                <th>Ladestation</th>
                <th className="table-number">
                  Energie
                </th>
                <th className="table-number">
                  Netto
                </th>
                <th className="table-number">
                  USt.
                </th>
                <th className="table-number">
                  Brutto
                </th>
              </tr>
            </thead>

            <tbody>
              {invoice.items.map((item) => (
                <tr key={item.id}>
                  <td>
                    {item.position_number}
                  </td>

                  <td>
                    <strong>
                      {item.description}
                    </strong>
                  </td>

                  <td>
                    {item.item_type ===
                    'charging_session' ? (
                      <>
                        {formatDateTime(
                          item.session_start,
                        )}
                        <br />
                        <span className="muted">
                          bis{' '}
                          {formatDateTime(
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
