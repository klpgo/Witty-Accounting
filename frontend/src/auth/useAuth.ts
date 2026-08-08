import { useContext } from 'react'

import {
  AuthContext,
  type AuthContextValue,
} from './authContext'

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext)

  if (context === undefined) {
    throw new Error(
      'useAuth muss innerhalb von AuthProvider verwendet werden.',
    )
  }

  return context
}
