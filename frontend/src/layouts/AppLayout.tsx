import {
  NavLink,
  Outlet,
  useNavigate,
} from 'react-router-dom'

import { useAuth } from '../auth/useAuth'

function AppLayout() {
  const navigate = useNavigate()
  const { user, signOut } = useAuth()

  const displayName = user
    ? `${user.first_name} ${user.last_name}`.trim()
    : 'Administrator'

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
          <div className="app-brand">
            <span className="app-brand-mark">
              WA
            </span>

            <div>
              <strong>Witty Accounting</strong>

              <span>
                Verwaltungsoberfläche
              </span>
            </div>
          </div>

          <nav
            className="app-nav"
            aria-label="Hauptnavigation"
          >
            <NavLink
              to="/"
              end
              className={({ isActive }) =>
                isActive
                  ? 'nav-link nav-link-active'
                  : 'nav-link'
              }
            >
              Dashboard
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
              RFID-Karten
            </NavLink>
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
