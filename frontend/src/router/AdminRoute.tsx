import {
  Navigate,
  Outlet,
} from 'react-router-dom'

import { useAuth } from '../auth/useAuth'

function AdminRoute() {
  const { user } = useAuth()

  if (user === null || !user.is_admin) {
    return (
      <Navigate
        to="/"
        replace
      />
    )
  }

  return <Outlet />
}

export default AdminRoute
