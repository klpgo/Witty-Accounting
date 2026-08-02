import {
  useEffect,
  useState,
} from 'react'
import { useNavigate } from 'react-router-dom'

import {
  DashboardApiError,
  getDashboard,
  type DashboardData,
} from '../api/dashboard'
import { getAccessToken } from '../auth/tokenStorage'
import { useAuth } from '../auth/useAuth'

function formatDateTime(
  value: string | null | undefined,
): string {
  if (!value) {
    return 'Noch kein Import'
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

function formatDate(
  value: string | null | undefined,
): string {
  if (!value) {
    return 'Noch keine Abrechnung'
  }

  const date = new Date(value)

  if (Number.isNaN(date.getTime())) {
    return value
  }

  return new Intl.DateTimeFormat('de-DE', {
    dateStyle: 'long',
  }).format(date)
}

function DashboardPage() {
  const navigate = useNavigate()
  const { user, signOut } = useAuth()

  const [dashboard, setDashboard] =
    useState<DashboardData | null>(null)
  const [isLoading, setIsLoading] =
    useState(true)
  const [isOffline, setIsOffline] =
    useState(false)

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

    async function loadDashboard(): Promise<void> {
      try {
        const loadedDashboard =
          await getDashboard(
            token,
            controller.signal,
          )

        setDashboard(loadedDashboard)
        setIsOffline(false)
      } catch (error) {
        if (
          error instanceof DOMException &&
          error.name === 'AbortError'
        ) {
          return
        }

        if (
          error instanceof DashboardApiError &&
          error.status === 401
        ) {
          signOut()
          navigate('/login', {
            replace: true,
          })
          return
        }

        setDashboard(null)
        setIsOffline(true)
      } finally {
        if (!controller.signal.aborted) {
          setIsLoading(false)
        }
      }
    }

    void loadDashboard()

    return () => {
      controller.abort()
    }
  }, [navigate, signOut])

  const isMaintenance =
    dashboard?.server_status === 'maintenance'

  const statusLabel = isLoading
    ? 'Status wird geprüft …'
    : isOffline
      ? 'Server offline'
      : isMaintenance
        ? 'Wartung'
        : 'Server online'

  const statusClassName = isLoading
    ? 'dashboard-status-checking'
    : isOffline
      ? 'dashboard-status-offline'
      : isMaintenance
        ? 'dashboard-status-maintenance'
        : 'dashboard-status-online'

  return (
    <div className="page dashboard-page">
      <header className="page-header">
        <div>
          <p className="eyebrow">
            Übersicht
          </p>

          <h1>Dashboard</h1>

          <p className="muted">
            Willkommen, {user?.first_name}.
          </p>
        </div>
      </header>

      <section className="dashboard-grid">
        <article className="card dashboard-status-card">
          <div>
            <p className="eyebrow">
              Systemstatus
            </p>

            <h2>{statusLabel}</h2>

            <p className="muted">
              {isLoading
                ? 'Die Verbindung zum Backend wird geprüft.'
                : isOffline
                  ? 'Das Backend ist derzeit nicht erreichbar.'
                  : isMaintenance
                    ? 'Das System befindet sich im Wartungsmodus.'
                    : 'Das System ist erreichbar und betriebsbereit.'}
            </p>
          </div>

          <span
            className={`dashboard-status-indicator ${statusClassName}`}
            aria-hidden="true"
          />
        </article>

        <article className="card dashboard-note-card">
          <p className="eyebrow">
            Mitteilung der Administration
          </p>

          {isLoading ? (
            <p className="muted">
              Mitteilungen werden geladen …
            </p>
          ) : isOffline ? (
            <p className="muted">
              Mitteilungen sind derzeit nicht verfügbar.
            </p>
          ) : dashboard?.admin_note ? (
            <p className="dashboard-note">
              {dashboard.admin_note}
            </p>
          ) : (
            <p className="muted">
              Derzeit liegen keine Mitteilungen vor.
            </p>
          )}
        </article>

        <article className="card dashboard-metric-card">
          <p className="eyebrow">
            Datenstand
          </p>

          <h2>
            {isLoading
              ? 'Wird geladen …'
              : isOffline
              ? 'Nicht verfügbar'
              : formatDateTime(
                  dashboard?.latest_charging_session_at,
                )}
          </h2>

          <p className="muted">
            Neuester importierter Ladevorgang
          </p>
        </article>

        <article className="card dashboard-metric-card">
          <p className="eyebrow">
            Abrechnungsstand
          </p>

          <h2>
            {isLoading
              ? 'Wird geladen …'
              : isOffline
              ? 'Nicht verfügbar'
              : formatDate(
                  dashboard?.invoiced_through,
                )}
          </h2>

          <p className="muted">
            Ladevorgänge abgerechnet bis
          </p>
        </article>

        <article className="card dashboard-version-card">
          <p className="eyebrow">
            Aktive Versionen
          </p>

          <dl className="dashboard-version-list">
            <div>
              <dt>Frontend</dt>
              <dd>v{__FRONTEND_VERSION__}</dd>
            </div>

            <div>
              <dt>Backend</dt>
              <dd>
                {isLoading
                  ? 'Wird geladen …'
                  : dashboard?.backend_version
                  ? `v${dashboard.backend_version}`
                  : 'Nicht verfügbar'}
              </dd>
            </div>
          </dl>
        </article>
      </section>
    </div>
  )
}

export default DashboardPage
