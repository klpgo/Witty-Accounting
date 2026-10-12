import { readApiError } from './errors'

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ??
  '/api'

export interface TokenResponse {
  access_token: string
  token_type: 'bearer'
}

export interface AuthenticatedUser {
  id: number
  email: string
  first_name: string
  last_name: string
  is_admin: boolean
  active: boolean
  // null = Standardsprache des Mandanten
  language?: string | null
}

interface PasswordResetRequestResponse {
  message: string
}

export async function login(
  email: string,
  password: string,
): Promise<TokenResponse> {
  const body = new URLSearchParams()

  body.set('username', email)
  body.set('password', password)

  const response = await fetch(
    `${API_BASE_URL}/auth/token`,
    {
      method: 'POST',
      headers: {
        'Content-Type':
          'application/x-www-form-urlencoded',
      },
      body,
    },
  )

  if (!response.ok) {
    throw new Error(
      await readApiError(response),
    )
  }

  return (await response.json()) as TokenResponse
}

export async function getCurrentUser(
  accessToken: string,
): Promise<AuthenticatedUser> {
  const response = await fetch(
    `${API_BASE_URL}/auth/me`,
    {
      headers: {
        Authorization: `Bearer ${accessToken}`,
      },
    },
  )

  if (!response.ok) {
    throw new Error(
      await readApiError(response),
    )
  }

  return (
    await response.json()
  ) as AuthenticatedUser
}

export async function requestPasswordReset(
  email: string,
): Promise<string> {
  const response = await fetch(
    `${API_BASE_URL}/auth/password-reset/request`,
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ email }),
    },
  )

  if (!response.ok) {
    throw new Error(
      await readApiError(response),
    )
  }

  const body =
    (await response.json()) as PasswordResetRequestResponse

  return body.message
}

export async function confirmPasswordReset(
  token: string,
  newPassword: string,
): Promise<void> {
  const response = await fetch(
    `${API_BASE_URL}/auth/password-reset/confirm`,
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        token,
        new_password: newPassword,
      }),
    },
  )

  if (!response.ok) {
    throw new Error(
      await readApiError(response),
    )
  }
}
