import {
  type FormEvent,
  useEffect,
  useState,
} from 'react'
import {
  Link,
  useNavigate,
} from 'react-router-dom'

import {
  createInvoiceDraft,
  InvoiceApiError,
} from '../api/invoices'
import {
  getGlobalSettings,
  SettingsApiError,
} from '../api/settings'
import {
  listUsers,
  UserApiError,
  type User,
} from '../api/users'
import { getAccessToken } from '../auth/tokenStorage'
import { useAuth } from '../auth/useAuth'
import { formatDate } from '../utils/dateFormat'
import { useTranslation } from '../i18n/useTranslation'

function padNumber(value: number): string {
  return String(value).padStart(2, '0')
}

function formatDateTimeLocal(
  date: Date,
): string {
  return [
    date.getFullYear(),
    '-',
    padNumber(date.getMonth() + 1),
    '-',
    padNumber(date.getDate()),
    'T',
    padNumber(date.getHours()),
    ':',
    padNumber(date.getMinutes()),
  ].join('')
}

function getDefaultPeriodStart(): string {
  const now = new Date()

  return formatDateTimeLocal(
    new Date(
      now.getFullYear(),
      now.getMonth(),
      1,
      0,
      0,
    ),
  )
}

function getDefaultPeriodEnd(): string {
  const now = new Date()

  return formatDateTimeLocal(
    new Date(
      now.getFullYear(),
      now.getMonth() + 1,
      1,
      0,
      0,
    ),
  )
}

function getUserLabel(user: User): string {
  const fullName = [
    user.first_name,
    user.last_name,
  ]
    .filter(Boolean)
    .join(' ')

  return `${fullName} – ${user.email}`
}


function InvoiceDraftCreatePage() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const { signOut } = useAuth()

  const [users, setUsers] =
    useState<User[]>([])

  const [selectedUserId, setSelectedUserId] =
    useState('')

  const [
    servicePeriodStart,
    setServicePeriodStart,
  ] = useState(getDefaultPeriodStart)

  const [
    servicePeriodEnd,
    setServicePeriodEnd,
  ] = useState(getDefaultPeriodEnd)

  const [isLoadingUsers, setIsLoadingUsers] =
    useState(true)

  const [isSubmitting, setIsSubmitting] =
    useState(false)

  const [billingStartDate, setBillingStartDate] =
    useState<string | null>(null)

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

    async function loadFormData(): Promise<void> {
      try {
        const [loadedUsers, globalSettings] =
          await Promise.all([
            listUsers(
              token,
              controller.signal,
            ),
            getGlobalSettings(
              token,
              controller.signal,
            ),
          ])

        const activeUsers = loadedUsers.filter(
          (user) => user.active,
        )

        setUsers(activeUsers)

        if (activeUsers.length > 0) {
          setSelectedUserId(
            String(activeUsers[0].id),
          )
        }

        setBillingStartDate(
          globalSettings.billing_start_date,
        )
      } catch (error) {
        if (
          error instanceof Error &&
          error.name === 'AbortError'
        ) {
          return
        }

        if (
          (error instanceof UserApiError ||
            error instanceof SettingsApiError) &&
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
            : t('draft.usersLoadFailed'),
        )
      } finally {
        if (!controller.signal.aborted) {
          setIsLoadingUsers(false)
        }
      }
    }

    void loadFormData()

    return () => {
      controller.abort()
    }
  }, [navigate, signOut])

  const billingStartDateTime =
    billingStartDate === null
      ? null
      : `${billingStartDate}T00:00`

  const periodIsBeforeBillingStart =
    billingStartDateTime !== null &&
    servicePeriodEnd <= billingStartDateTime

  const periodStartsBeforeBillingStart =
    billingStartDateTime !== null &&
    servicePeriodStart < billingStartDateTime &&
    servicePeriodEnd > billingStartDateTime

  async function handleSubmit(
    event: FormEvent<HTMLFormElement>,
  ): Promise<void> {
    event.preventDefault()

    const userId = Number(selectedUserId)

    if (
      !Number.isInteger(userId) ||
      userId <= 0
    ) {
      setErrorMessage(
        t('draft.userMissing'),
      )
      return
    }

    if (
      servicePeriodStart >= servicePeriodEnd
    ) {
      setErrorMessage(
        t('draft.endBeforeStart'),
      )
      return
    }

    if (periodIsBeforeBillingStart) {
      setErrorMessage(
        t('draft.beforeBillingStart'),
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
      const invoice = await createInvoiceDraft(
        accessToken,
        {
          user_id: userId,
          service_period_start:
            servicePeriodStart,
          service_period_end:
            servicePeriodEnd,
        },
      )

      navigate(
        `/invoices/${invoice.id}`,
        {
          replace: true,
        },
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
          : t('draft.failed'),
      )
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <div className="page invoice-create-page">
      <Link
        className="back-link"
        to="/invoices"
      >
        {t('invoiceDetail.back')}
      </Link>

      <header className="page-header create-page-header">
        <div>
          <p className="eyebrow">
            {t('invoices.eyebrow')}
          </p>

          <h1>{t('draft.title')}</h1>

          <p className="muted">
            {t('draft.intro')}
          </p>
        </div>
      </header>

      <section className="card create-form-card">
        {isLoadingUsers ? (
          <p className="muted">
            {t('draft.loadingUsers')}
          </p>
        ) : (
          <form
            className="invoice-create-form"
            onSubmit={handleSubmit}
          >
            <label className="form-field">
              <span>{t('draft.user')}</span>

              <select
                value={selectedUserId}
                onChange={(event) => {
                  setSelectedUserId(
                    event.target.value,
                  )
                }}
                disabled={
                  users.length === 0 ||
                  isSubmitting
                }
                required
              >
                {users.length === 0 && (
                  <option value="">
                    {t('draft.noActiveUsers')}
                  </option>
                )}

                {users.map((user) => (
                  <option
                    key={user.id}
                    value={user.id}
                  >
                    {getUserLabel(user)}
                  </option>
                ))}
              </select>
            </label>

            <div className="form-grid">
              <label className="form-field">
                <span>
                  {t('draft.periodFrom')}
                </span>

                <input
                  type="datetime-local"
                  value={servicePeriodStart}
                  onChange={(event) => {
                    setServicePeriodStart(
                      event.target.value,
                    )
                  }}
                  disabled={isSubmitting}
                  required
                />
              </label>

              <label className="form-field">
                <span>
                  {t('draft.periodTo')}
                </span>

                <input
                  type="datetime-local"
                  value={servicePeriodEnd}
                  onChange={(event) => {
                    setServicePeriodEnd(
                      event.target.value,
                    )
                  }}
                  disabled={isSubmitting}
                  required
                />
              </label>
            </div>

            {billingStartDate !== null && (
              <div
                className={[
                  'billing-start-notice',
                  periodIsBeforeBillingStart ||
                  periodStartsBeforeBillingStart
                    ? 'billing-start-notice-warning'
                    : '',
                ]
                  .filter(Boolean)
                  .join(' ')}
                role={
                  periodIsBeforeBillingStart
                    ? 'alert'
                    : 'note'
                }
              >
                <strong>
                  {t('draft.billingStart', {
                    date: formatDate(billingStartDate),
                  })}
                </strong>

                <span>
                  {' '}
                  {periodIsBeforeBillingStart
                    ? t('draft.billingStart.before')
                    : periodStartsBeforeBillingStart
                      ? t('draft.billingStart.startsBefore')
                      : t('draft.billingStart.info')}
                </span>

                {periodIsBeforeBillingStart && (
                  <Link to="/admin/settings">
                    {t('draft.billingStart.change')}
                  </Link>
                )}
              </div>
            )}

            {errorMessage && (
              <p
                className="form-error"
                role="alert"
              >
                {errorMessage}
              </p>
            )}

            <div className="form-actions">
              <Link
                className="button button-secondary"
                to="/invoices"
              >
                Abbrechen
              </Link>

              <button
                className="button button-primary"
                type="submit"
                disabled={
                  isSubmitting ||
                  users.length === 0 ||
                  periodIsBeforeBillingStart
                }
              >
                {isSubmitting
                  ? t('draft.submitting')
                  : t('draft.submit')}
              </button>
            </div>
          </form>
        )}
      </section>
    </div>
  )
}

export default InvoiceDraftCreatePage
