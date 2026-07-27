import {
  type ReactNode,
  useEffect,
  useState,
} from 'react'

import {
  getCurrentUser,
  login as requestLogin,
  type AuthenticatedUser,
} from '../api/auth'
import {
  clearAccessToken,
  getAccessToken,
  setAccessToken,
} from './tokenStorage'
import {
  AuthContext,
  type AuthStatus,
} from './authContext'

interface AuthProviderProps {
  children: ReactNode
}

export function AuthProvider({
  children,
}: AuthProviderProps) {
  const [user, setUser] =
    useState<AuthenticatedUser | null>(null)

  const [status, setStatus] =
    useState<AuthStatus>('loading')

  useEffect(() => {
    const storedAccessToken = getAccessToken()

    if (storedAccessToken === null) {
      setStatus('unauthenticated')
      return
    }

    const accessToken = storedAccessToken
    let isCancelled = false

    async function restoreSession() {
      try {
        const currentUser =
          await getCurrentUser(accessToken)

        if (!currentUser.is_admin) {
          throw new Error(
            'Administratorrechte erforderlich.',
          )
        }

        if (!isCancelled) {
          setUser(currentUser)
          setStatus('authenticated')
        }
      } catch {
        clearAccessToken()

        if (!isCancelled) {
          setUser(null)
          setStatus('unauthenticated')
        }
      }
    }

    void restoreSession()

    return () => {
      isCancelled = true
    }
  }, [])

  async function signIn(
    email: string,
    password: string,
  ): Promise<void> {
    const token = await requestLogin(
      email,
      password,
    )

    const currentUser = await getCurrentUser(
      token.access_token,
    )

    if (!currentUser.is_admin) {
      throw new Error(
        'Für das Web-Interface sind Administratorrechte erforderlich.',
      )
    }

    setAccessToken(token.access_token)
    setUser(currentUser)
    setStatus('authenticated')
  }

  function signOut(): void {
    clearAccessToken()
    setUser(null)
    setStatus('unauthenticated')
  }

  return (
    <AuthContext.Provider
      value={{
        user,
        status,
        signIn,
        signOut,
      }}
    >
      {children}
    </AuthContext.Provider>
  )
}
