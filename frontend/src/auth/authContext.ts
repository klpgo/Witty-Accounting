import { createContext } from 'react'

import type { AuthenticatedUser } from '../api/auth'

export type AuthStatus =
  | 'loading'
  | 'authenticated'
  | 'unauthenticated'

export interface AuthContextValue {
  user: AuthenticatedUser | null
  status: AuthStatus
  signIn: (
    email: string,
    password: string,
  ) => Promise<void>
  signOut: () => void
  updateAuthenticatedUser: (
    user: AuthenticatedUser,
  ) => void
}

export const AuthContext =
  createContext<AuthContextValue | undefined>(
    undefined,
  )
