import {
  Navigate,
  Outlet,
  useLocation,
} from 'react-router-dom'

import { useAuth } from '../auth/useAuth'
import { useAppSettings } from '../settings/useAppSettings'
import { useTranslation } from '../i18n/useTranslation'

function ProtectedRoute() {
  const { t } = useTranslation()
  const { tenantName } = useAppSettings()
  const location = useLocation()
  const { status, user } = useAuth()

  if (status === 'loading') {
    return (
      <main className="page page-centered">
        <section className="card loading-card">
          <p className="eyebrow">
            {tenantName}
          </p>

          <h1>{t('common.sessionCheck.title')}</h1>

          <p className="muted">
            {t('common.sessionCheck.text')}
          </p>
        </section>
      </main>
    )
  }

  if (
    status !== 'authenticated' ||
    user === null
  ) {
    return (
      <Navigate
        to="/login"
        replace
        state={{
          from: location.pathname,
        }}
      />
    )
  }

  return <Outlet />
}

export default ProtectedRoute
