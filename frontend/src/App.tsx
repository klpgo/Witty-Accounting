import {
  Navigate,
  Route,
  Routes,
} from 'react-router-dom'

import AppLayout from './layouts/AppLayout'
import DashboardPage from './pages/DashboardPage'
import InvoicesPage from './pages/InvoicesPage'
import LoginPage from './pages/LoginPage'
import ProtectedRoute from './router/ProtectedRoute'
import InvoiceDetailPage from './pages/InvoiceDetailPage'
import InvoiceDraftCreatePage from './pages/InvoiceDraftCreatePage'
import AdminUsersPage from './pages/AdminUsersPage'
import AdminRFIDCardsPage from './pages/AdminRFIDCardsPage'
import AdminSettingsPage from './pages/AdminSettingsPage'
import AdminImportPage from './pages/AdminImportPage'
import AdminRoute from './router/AdminRoute'
import ProfilePage from './pages/ProfilePage'
import ChargingSessionsPage from './pages/ChargingSessionsPage'

function App() {
  return (
    <Routes>
      <Route
        path="/login"
        element={<LoginPage />}
      />

      <Route element={<ProtectedRoute />}>
        <Route element={<AppLayout />}>
          <Route
            index
            element={<DashboardPage />}
          />
          <Route
            path="profile"
            element={<ProfilePage />}
          />
          <Route element={<AdminRoute />}>
            <Route
              path="admin/users"
              element={<AdminUsersPage />}
            />

            <Route
              path="admin/rfid-cards"
              element={<AdminRFIDCardsPage />}
            />

            <Route
              path="admin/import"
              element={<AdminImportPage />}
            />

            <Route
              path="admin/settings"
              element={<AdminSettingsPage />}
            />

            <Route
              path="invoices/new"
              element={<InvoiceDraftCreatePage />}
            />
          </Route>
          <Route
            path="charging-sessions"
            element={<ChargingSessionsPage />}
          />
          <Route
            path="invoices"
            element={<InvoicesPage />}
          />

          <Route
            path="invoices/:invoiceId"
            element={<InvoiceDetailPage />}
          />
        </Route>
      </Route>

      <Route
        path="*"
        element={
          <Navigate
            to="/"
            replace
          />
        }
      />
    </Routes>
  )
}

export default App
