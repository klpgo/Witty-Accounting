import {
  NavLink,
  Outlet,
  useNavigate,
} from 'react-router-dom'

import { useAuth } from '../auth/useAuth'
import { useAppSettings } from '../settings/useAppSettings'

function AppLayout() {
  const { appName } = useAppSettings()
  const navigate = useNavigate()
  const { user, signOut } = useAuth()

  const displayName = user
    ? `${user.first_name} ${user.last_name}`.trim()
    : 'Administrator'

  const brandMark =
    appName
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
            aria-label="Zum Dashboard"
          >
            <span className="app-brand-mark">
              {brandMark}
            </span>

            <div>
              <strong>{appName}</strong>

              <span>
                Verwaltungsoberfläche
              </span>
            </div>
          </NavLink>

          <nav
            className="app-nav"
            aria-label="Hauptnavigation"
          >

            {!user?.is_admin && (
              <NavLink
                to="/profile"
                className={({ isActive }) =>
                  isActive
                    ? 'nav-link nav-link-active'
                    : 'nav-link'
                }
              >
                Meine Daten
              </NavLink>
            )}
            <NavLink
              to="/charging-sessions"
              className={({ isActive }) =>
                isActive
                  ? 'nav-link nav-link-active'
                  : 'nav-link'
              }
            >
              Ladevorgänge
            </NavLink>
            <NavLink
              to="/invoices"
              className={({ isActive }) =>
                  isActive
                  ? 'nav-link nav-link-active'
                  : 'nav-link'
              }
            >
              Rechnungen
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
                Benutzer
              </NavLink>
              <NavLink
                to="/admin/rfid-cards"
                className={({ isActive }) =>
                  isActive
                    ? 'nav-link nav-link-active'
                    : 'nav-link'
                }
              >
                Ladekarten
              </NavLink>
              <NavLink
                to="/admin/import"
                className={({ isActive }) =>
                  isActive
                    ? 'nav-link nav-link-active'
                    : 'nav-link'
                }
              >
                Datenimport
              </NavLink>
              <NavLink
                to="/admin/settings"
                className={({ isActive }) =>
                  isActive
                    ? 'nav-link nav-link-active'
                    : 'nav-link'
                }
              >
                Einstellungen
              </NavLink>
              </>
            )}
          </nav>

          <div className="user-menu">
            <div className="user-details">
              <strong>{displayName}</strong>

              <span>{user?.email}</span>
            </div>

            <button
              className="button button-secondary"
              type="button"
              onClick={handleSignOut}
            >
              Abmelden
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
