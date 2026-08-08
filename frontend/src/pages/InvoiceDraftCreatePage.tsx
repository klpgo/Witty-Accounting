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
  listUsers,
  UserApiError,
  type User,
} from '../api/users'
import { getAccessToken } from '../auth/tokenStorage'
import { useAuth } from '../auth/useAuth'

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
      0,
      23,
      59,
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

    async function loadUsers(): Promise<void> {
      try {
        const loadedUsers = await listUsers(
          token,
          controller.signal,
        )

        const activeUsers = loadedUsers.filter(
          (user) => user.active,
        )

        setUsers(activeUsers)

        if (activeUsers.length > 0) {
          setSelectedUserId(
            String(activeUsers[0].id),
          )
        }
      } catch (error) {
        if (
          error instanceof Error &&
          error.name === 'AbortError'
        ) {
          return
        }

        if (
          error instanceof UserApiError &&
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
            : 'Die Benutzer konnten nicht geladen werden.',
        )
      } finally {
        if (!controller.signal.aborted) {
          setIsLoadingUsers(false)
        }
      }
    }

    void loadUsers()

    return () => {
      controller.abort()
    }
  }, [navigate, signOut])

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
        'Bitte wähle einen Benutzer aus.',
      )
      return
    }

    if (
      servicePeriodStart >= servicePeriodEnd
    ) {
      setErrorMessage(
        'Das Ende des Leistungszeitraums muss nach dem Beginn liegen.',
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
          : 'Der Rechnungsentwurf konnte nicht erstellt werden.',
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
        ← Zurück zu den Rechnungen
      </Link>

      <header className="page-header create-page-header">
        <div>
          <p className="eyebrow">
            Abrechnung
          </p>

          <h1>Rechnungsentwurf erstellen</h1>

          <p className="muted">
            Alle abrechenbaren Ladevorgänge des
            gewählten Benutzers im angegebenen
            Zeitraum werden übernommen.
          </p>
        </div>
      </header>

      <section className="card create-form-card">
        {isLoadingUsers ? (
          <p className="muted">
            Benutzer werden geladen …
          </p>
        ) : (
          <form
            className="invoice-create-form"
            onSubmit={handleSubmit}
          >
            <label className="form-field">
              <span>Benutzer</span>

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
                    Keine aktiven Benutzer vorhanden
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
                  Leistungszeitraum von
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
                  Leistungszeitraum bis
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
                  users.length === 0
                }
              >
                {isSubmitting
                  ? 'Entwurf wird erstellt …'
                  : 'Entwurf erstellen'}
              </button>
            </div>
          </form>
        )}
      </section>
    </div>
  )
}

export default InvoiceDraftCreatePage
