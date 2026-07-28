import {
  useEffect,
  useState,
} from 'react'
import {
  Link,
  useNavigate,
} from 'react-router-dom'

import {
  InvoiceApiError,
  listInvoices,
  type Invoice,
} from '../api/invoices'
import { getAccessToken } from '../auth/tokenStorage'
import { useAuth } from '../auth/useAuth'


function formatCurrency(
  value: string | number,
  currency: string,
): string {
  const numericValue = Number(value)

  if (!Number.isFinite(numericValue)) {
    return '–'
  }

  return new Intl.NumberFormat(
    'de-DE',
    {
      style: 'currency',
      currency,
    },
  ).format(numericValue)
}

function formatDate(
  value: string | null,
): string {
  if (value === null) {
    return '–'
  }

  const date = new Date(
    `${value}T00:00:00`,
  )

  if (Number.isNaN(date.getTime())) {
    return value
  }

  return new Intl.DateTimeFormat(
    'de-DE',
  ).format(date)
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
      return 'Storno'
    default:
      return documentType
  }
}

function InvoicesPage() {
  const navigate = useNavigate()
  const { signOut } = useAuth()

  const [invoices, setInvoices] =
    useState<Invoice[]>([])

  const [isLoading, setIsLoading] =
    useState(true)

  const [
    errorMessage,
    setErrorMessage,
  ] = useState<string | null>(null)

  useEffect(() => {
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

    async function loadInvoices(): Promise<void> {
      try {
        const loadedInvoices =
          await listInvoices(
            token,
            controller.signal,
          )

        setInvoices(loadedInvoices)
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
            : 'Die Rechnungen konnten nicht geladen werden.',
        )
      } finally {
        setIsLoading(false)
      }
    }

    void loadInvoices()

    return () => {
      controller.abort()
    }
  }, [navigate, signOut])

  return (
    <div className="page invoices-page">
      <header className="page-header">
        <div>
          <p className="eyebrow">
            Abrechnung
          </p>

          <h1>Rechnungen</h1>

          <p className="muted">
            Entwürfe, finalisierte Rechnungen
            und Stornobelege.
          </p>
        </div>
      </header>

      {isLoading && (
        <section className="card">
          <p className="muted">
            Rechnungen werden geladen …
          </p>
        </section>
      )}

      {!isLoading && errorMessage && (
        <section
          className="card form-error"
          role="alert"
        >
          {errorMessage}
        </section>
      )}

      {!isLoading &&
        !errorMessage &&
        invoices.length === 0 && (
          <section className="card">
            <h2>Keine Rechnungen vorhanden</h2>

            <p className="muted">
              Es wurden noch keine
              Rechnungsentwürfe erstellt.
            </p>
          </section>
        )}

      {!isLoading &&
        !errorMessage &&
        invoices.length > 0 && (
          <section className="card table-card">
            <div className="table-scroll">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Nummer</th>
                    <th>Art</th>
                    <th>Empfänger</th>
                    <th>Status</th>
                    <th>Rechnungsdatum</th>
                    <th>Fällig</th>
                    <th className="table-number">
                      Gesamt
                    </th>
                  </tr>
                </thead>

                <tbody>
                  {invoices.map((invoice) => (
                    <tr key={invoice.id}>
                      <td>
                        <Link
                          className="table-link"
                          to={`/invoices/${invoice.id}`}
                        >
                          {invoice.invoice_number ??
                              `Entwurf #${invoice.id}`}
                        </Link>
                        <strong>
                          {invoice.invoice_number ??
                            `Entwurf #${invoice.id}`}
                        </strong>
                      </td>

                      <td>
                        {getDocumentTypeLabel(
                          invoice.document_type,
                        )}
                      </td>

                      <td>
                        {invoice.recipient_name}
                      </td>

                      <td>
                        <span
                          className={
                            invoice.status ===
                            'finalized'
                              ? 'status-badge status-finalized'
                              : 'status-badge status-draft'
                          }
                        >
                          {getStatusLabel(
                            invoice.status,
                          )}
                        </span>
                      </td>

                      <td>
                        {formatDate(
                          invoice.issue_date,
                        )}
                      </td>

                      <td>
                        {formatDate(
                          invoice.due_date,
                        )}
                      </td>

                      <td className="table-number">
                        {formatCurrency(
                          invoice.total_gross,
                          invoice.currency,
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        )}
    </div>
  )
}

export default InvoicesPage
