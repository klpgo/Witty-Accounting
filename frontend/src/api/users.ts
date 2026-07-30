const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ??
  'http://localhost:8000'

export interface User {
  id: number
  email: string
  salutation: string | null
  first_name: string
  last_name: string
  address: string | null
  phone: string | null
  invoice_delivery_email: boolean
  invoice_delivery_post: boolean
  active: boolean
  is_admin: boolean
  created_at: string
  updated_at: string
}

export interface UserAdminUpdate {
  email?: string
  first_name?: string
  last_name?: string
  address?: string | null
  invoice_delivery_email?: boolean
  invoice_delivery_post?: boolean
  active?: boolean
  is_admin?: boolean
}

interface ApiErrorResponse {
  detail?: string
}

export class UserApiError extends Error {
  readonly status: number

  constructor(
    message: string,
    status: number,
  ) {
    super(message)
    this.name = 'UserApiError'
    this.status = status
  }
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
    // Die Antwort enthielt kein JSON.
  }

  return `Anfrage fehlgeschlagen (${response.status}).`
}

function createHeaders(
  accessToken: string,
  includeContentType = false,
): HeadersInit {
  return {
    Authorization: `Bearer ${accessToken}`,
    ...(includeContentType
      ? {
          'Content-Type': 'application/json',
        }
      : {}),
  }
}

export async function listUsers(
  accessToken: string,
  signal?: AbortSignal,
): Promise<User[]> {
  const response = await fetch(
    `${API_BASE_URL}/users`,
    {
      headers: createHeaders(accessToken),
      signal,
    },
  )

  if (!response.ok) {
    throw new UserApiError(
      await getErrorMessage(response),
      response.status,
    )
  }

  return (await response.json()) as User[]
}

export async function getUser(
  accessToken: string,
  userId: number,
  signal?: AbortSignal,
): Promise<User> {
  const response = await fetch(
    `${API_BASE_URL}/users/${userId}`,
    {
      headers: createHeaders(accessToken),
      signal,
    },
  )

  if (!response.ok) {
    throw new UserApiError(
      await getErrorMessage(response),
      response.status,
    )
  }

  return (await response.json()) as User
}

export async function updateUser(
  accessToken: string,
  userId: number,
  payload: UserAdminUpdate,
): Promise<User> {
  const response = await fetch(
    `${API_BASE_URL}/users/${userId}`,
    {
      method: 'PATCH',
      headers: createHeaders(
        accessToken,
        true,
      ),
      body: JSON.stringify(payload),
    },
  )

  if (!response.ok) {
    throw new UserApiError(
      await getErrorMessage(response),
      response.status,
    )
  }

  return (await response.json()) as User
}

export async function resetUserPassword(
  accessToken: string,
  userId: number,
  newPassword: string,
): Promise<void> {
  const response = await fetch(
    `${API_BASE_URL}/users/${userId}/password`,
    {
      method: 'POST',
      headers: createHeaders(
        accessToken,
        true,
      ),
      body: JSON.stringify({
        new_password: newPassword,
      }),
    },
  )

  if (!response.ok) {
    throw new UserApiError(
      await getErrorMessage(response),
      response.status,
    )
  }
}
