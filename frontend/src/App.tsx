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
