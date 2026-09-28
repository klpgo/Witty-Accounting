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
import { getDisplayLocale } from '../utils/dateFormat'
import { useTranslation } from '../i18n/useTranslation'

function formatDateTime(
  value: string | null | undefined,
  emptyText: string,
): string {
  if (!value) {
    return emptyText
  }

  const date = new Date(value)

  if (Number.isNaN(date.getTime())) {
    return value
  }

  return new Intl.DateTimeFormat(getDisplayLocale(), {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(date)
}

function formatDate(
  value: string | null | undefined,
  emptyText: string,
): string {
  if (!value) {
    return emptyText
  }

  const date = new Date(value)

  if (Number.isNaN(date.getTime())) {
    return value
  }

  return new Intl.DateTimeFormat(getDisplayLocale(), {
    dateStyle: 'long',
  }).format(date)
}

function DashboardPage() {
  const { t } = useTranslation()
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
    ? t('dashboard.status.checking')
    : isOffline
      ? t('dashboard.status.offline')
      : isMaintenance
        ? t('dashboard.status.maintenance')
        : t('dashboard.status.online')

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
            {t('dashboard.eyebrow')}
          </p>

          <h1>{t('dashboard.title')}</h1>

          <p className="muted">
            {t('dashboard.welcome', { name: user?.first_name ?? '' })}
          </p>
        </div>
      </header>

      <section className="dashboard-grid">
        <article className="card dashboard-status-card">
          <div>
            <p className="eyebrow">
              {t('dashboard.status.eyebrow')}
            </p>

            <h2>{statusLabel}</h2>

            <p className="muted">
              {isLoading
                ? t('dashboard.status.checkingText')
                : isOffline
                  ? t('dashboard.status.offlineText')
                  : isMaintenance
                    ? t('dashboard.status.maintenanceText')
                    : t('dashboard.status.onlineText')}
            </p>
          </div>

          <span
            className={`dashboard-status-indicator ${statusClassName}`}
            aria-hidden="true"
          />
        </article>

        <article className="card dashboard-note-card">
          <p className="eyebrow">
            {t('dashboard.messages.eyebrow')}
          </p>

          {isLoading ? (
            <p className="muted">
              {t('dashboard.messages.loading')}
            </p>
          ) : isOffline ? (
            <p className="muted">
              {t('dashboard.messages.unavailable')}
            </p>
          ) : dashboard?.admin_note ? (
            <p className="dashboard-note">
              {dashboard.admin_note}
            </p>
          ) : (
            <p className="muted">
              {t('dashboard.messages.none')}
            </p>
          )}
        </article>

        <article className="card dashboard-metric-card">
          <p className="eyebrow">
            {t('dashboard.dataStatus.eyebrow')}
          </p>

          <h2>
            {isLoading
              ? t('common.loading')
              : isOffline
              ? t('common.notAvailable')
              : formatDateTime(
                  dashboard?.latest_charging_session_at,
                  t('dashboard.noImport'),
                )}
          </h2>

          <p className="muted">
            {t('dashboard.dataStatus.text')}
          </p>
        </article>

        <article className="card dashboard-metric-card">
          <p className="eyebrow">
            {t('dashboard.billing.eyebrow')}
          </p>

          <h2>
            {isLoading
              ? t('common.loading')
              : isOffline
              ? t('common.notAvailable')
              : formatDate(
                  dashboard?.invoiced_through,
                  t('dashboard.noBilling'),
                )}
          </h2>

          <p className="muted">
            {t('dashboard.billing.text')}
          </p>
        </article>

        <article className="card dashboard-version-card">
          <p className="eyebrow">
            {t('dashboard.versions.eyebrow')}
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
                  ? t('common.loading')
                  : dashboard?.backend_version
                  ? `v${dashboard.backend_version}`
                  : t('common.notAvailable')}
              </dd>
            </div>
          </dl>
        </article>
      </section>
    </div>
  )
}

export default DashboardPage
