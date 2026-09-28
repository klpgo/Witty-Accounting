import {
  NavLink,
  Outlet,
  useNavigate,
} from 'react-router-dom'

import { useAuth } from '../auth/useAuth'
import { useAppSettings } from '../settings/useAppSettings'
import { useTranslation } from '../i18n/useTranslation'

function AppLayout() {
  const { t } = useTranslation()
  const { tenantName } = useAppSettings()
  const navigate = useNavigate()
  const { user, signOut } = useAuth()

  const displayName = user
    ? `${user.first_name} ${user.last_name}`.trim()
    : t('layout.fallbackName')

  const brandMark =
    tenantName
      .split(/[\s-]+/)
      .filter(Boolean)
      .slice(0, 2)
      .map((part) =>
        part.charAt(0).toUpperCase(),
      )
      .join('') || 'WA'

  function handleSignOut(): void {
    signOut()

    navigate('/login', {
      replace: true,
    })
  }

  return (
    <div className="app-shell">
      <header className="app-header">
        <div className="app-header-content">
          <NavLink
            to="/"
            end
            className="app-brand"
            aria-label={t('layout.brandAria')}
          >
            <span className="app-brand-mark">
              {brandMark}
            </span>

            <div>
              <strong>{tenantName}</strong>

              <span>
                {t('layout.subtitle')}
              </span>
            </div>
          </NavLink>

          <nav
            className="app-nav"
            aria-label={t('layout.navAria')}
          >
            <NavLink
              to="/charging-sessions"
              className={({ isActive }) =>
                isActive
                  ? 'nav-link nav-link-active'
                  : 'nav-link'
              }
            >
              {t('layout.nav.chargingSessions')}
            </NavLink>
            <NavLink
              to="/invoices"
              className={({ isActive }) =>
                  isActive
                  ? 'nav-link nav-link-active'
                  : 'nav-link'
              }
            >
              {t('layout.nav.invoices')}
            </NavLink>

            {user?.is_admin && (
              <>
              <NavLink
                to="/admin/users"
                className={({ isActive }) =>
                  isActive
                    ? 'nav-link nav-link-active'
                    : 'nav-link'
                }
              >
                {t('layout.nav.users')}
              </NavLink>
              <NavLink
                to="/admin/rfid-cards"
                className={({ isActive }) =>
                  isActive
                    ? 'nav-link nav-link-active'
                    : 'nav-link'
                }
              >
                {t('layout.nav.rfidCards')}
              </NavLink>
              <NavLink
                to="/admin/import"
                className={({ isActive }) =>
                  isActive
                    ? 'nav-link nav-link-active'
                    : 'nav-link'
                }
              >
                {t('layout.nav.import')}
              </NavLink>
              <NavLink
                to="/admin/settings"
                className={({ isActive }) =>
                  isActive
                    ? 'nav-link nav-link-active'
                    : 'nav-link'
                }
              >
                {t('layout.nav.settings')}
              </NavLink>
              </>
            )}
          </nav>

          <div className="user-menu">
            <NavLink
              to="/profile"
              className={({ isActive }) =>
                isActive
                  ? 'user-menu-trigger user-menu-trigger-active'
                  : 'user-menu-trigger'
              }
              aria-label={t('layout.profileAria')}
            >
              <span className="user-details">
                <strong>{displayName}</strong>

                <span>{user?.email}</span>
              </span>
            </NavLink>

            <button
              className="button button-secondary"
              type="button"
              onClick={handleSignOut}
            >
              {t('layout.signOut')}
            </button>
          </div>
        </div>
      </header>

      <main className="app-main">
        <Outlet />
      </main>
    </div>
  )
}

export default AppLayout
