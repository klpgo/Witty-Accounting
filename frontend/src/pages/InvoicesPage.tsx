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
import { formatDate } from '../utils/dateFormat'
import {
  formatCurrency,
} from '../utils/numberFormat'
import {
  documentTypeLabel,
  invoiceStatusLabel,
} from '../i18n/invoiceLabels'
import { useTranslation } from '../i18n/useTranslation'


function InvoicesPage() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const { user, signOut } = useAuth()
  const isAdmin = user?.is_admin === true

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
            : t('invoices.loadFailed'),
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
            {t('invoices.eyebrow')}
          </p>

          <h1>{t('invoices.title')}</h1>

          <p className="muted">
            {isAdmin
              ? t('invoices.intro.admin')
              : t('invoices.intro.user')}
          </p>
        </div>
        {isAdmin && (
          <Link
            className="button button-primary"
            to="/invoices/new"
          >
            {t('invoices.createDraft')}
          </Link>
        )}
      </header>

      {isLoading && (
        <section className="card">
          <p className="muted">
            {t('invoices.loading')}
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
            <h2>{t('invoices.empty.title')}</h2>

            <p className="muted">
              {isAdmin
                ? t('invoices.empty.admin')
                : t('invoices.empty.user')}
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
                    <th>{t('invoices.col.number')}</th>
                    <th>{t('invoices.col.type')}</th>
                    <th>{t('invoices.col.recipient')}</th>
                    <th>{t('invoices.col.status')}</th>
                    <th>{t('invoices.col.issueDate')}</th>
                    <th>{t('invoices.col.due')}</th>
                    <th className="table-number">
                      {t('invoices.col.total')}
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
                            t('common.draftNumber', {
                              id: invoice.id,
                            })}
                        </Link>
                      </td>

                      <td>
                        {documentTypeLabel(
                          t,
                          invoice.document_type,
                          true,
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
                          {invoiceStatusLabel(
                            t,
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
