const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ??
  'http://localhost:8000'

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
}

interface ApiErrorResponse {
  detail?: string
}

async function getErrorMessage(
  response: Response,
): Promise<string> {
  try {
    const body =
      (await response.json()) as ApiErrorResponse

    if (body.detail) {
      return body.detail
    }
  } catch {
    // Response did not contain JSON.
  }

  return `Anfrage fehlgeschlagen (${response.status}).`
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
      await getErrorMessage(response),
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
      await getErrorMessage(response),
    )
  }

  return (
    await response.json()
  ) as AuthenticatedUser
}
