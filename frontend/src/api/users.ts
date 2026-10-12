import { readApiError } from './errors'

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ??
  '/api'

export interface User {
  id: number
  email: string
  first_name: string
  last_name: string
  address: string | null
  phone: string | null
  invoice_delivery_email: boolean
  invoice_delivery_post: boolean
  active: boolean
  is_admin: boolean
  last_login: string | null
  created_at: string
  updated_at: string
  language?: string | null
}

export interface UserProfileUpdate {
  email?: string
  first_name?: string
  last_name?: string
  address?: string | null
  phone?: string | null
  invoice_delivery_email?: boolean
  invoice_delivery_post?: boolean
  // null = Standardsprache des Mandanten
  language?: string | null
}

export interface UserAdminUpdate
  extends UserProfileUpdate {
  active?: boolean
  is_admin?: boolean
}

export interface UserCreate
  extends UserAdminUpdate {
  email: string
  first_name: string
  last_name: string
}

export type InvoiceDeliveryMethod =
  | 'email'
  | 'post'
  | 'portal'

export function getInvoiceDeliveryMethod(
  user: Pick<
    User,
    | 'invoice_delivery_email'
    | 'invoice_delivery_post'
  >,
): InvoiceDeliveryMethod {
  if (user.invoice_delivery_post) {
    return 'post'
  }

  if (user.invoice_delivery_email) {
    return 'email'
  }

  return 'portal'
}

export function getInvoiceDeliveryFlags(
  method: InvoiceDeliveryMethod,
): Pick<
  User,
  | 'invoice_delivery_email'
  | 'invoice_delivery_post'
> {
  return {
    invoice_delivery_email: method === 'email',
    invoice_delivery_post: method === 'post',
  }
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

export async function getOwnProfile(
  accessToken: string,
  signal?: AbortSignal,
): Promise<User> {
  const response = await fetch(
    `${API_BASE_URL}/users/me`,
    {
      headers: createHeaders(accessToken),
      signal,
    },
  )

  if (!response.ok) {
    throw new UserApiError(
      await readApiError(response),
      response.status,
    )
  }

  return (await response.json()) as User
}

export async function updateOwnProfile(
  accessToken: string,
  payload: UserProfileUpdate,
): Promise<User> {
  const response = await fetch(
    `${API_BASE_URL}/users/me`,
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
      await readApiError(response),
      response.status,
    )
  }

  return (await response.json()) as User
}

export async function changeOwnPassword(
  accessToken: string,
  currentPassword: string,
  newPassword: string,
): Promise<void> {
  const response = await fetch(
    `${API_BASE_URL}/users/me/password`,
    {
      method: 'POST',
      headers: createHeaders(
        accessToken,
        true,
      ),
      body: JSON.stringify({
        current_password: currentPassword,
        new_password: newPassword,
      }),
    },
  )

  if (!response.ok) {
    throw new UserApiError(
      await readApiError(response),
      response.status,
    )
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
      await readApiError(response),
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
      await readApiError(response),
      response.status,
    )
  }

  return (await response.json()) as User
}

export async function createUser(
  accessToken: string,
  payload: UserCreate,
): Promise<User> {
  const response = await fetch(
    `${API_BASE_URL}/users`,
    {
      method: 'POST',
      headers: createHeaders(
        accessToken,
        true,
      ),
      body: JSON.stringify(payload),
    },
  )

  if (!response.ok) {
    throw new UserApiError(
      await readApiError(response),
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
      await readApiError(response),
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
      await readApiError(response),
      response.status,
    )
  }
}

export interface UserDeletionBlocker {
  code: string
  count: number
  message: string
  discardable: boolean
}

export interface UserDeletionCheck {
  user_id: number
  can_delete: boolean
  can_delete_with_discard: boolean
  blockers: UserDeletionBlocker[]
  charging_sessions: number
  base_fees: number
  rfid_assignments: number
  invoices_kept: number
}

export async function getUserDeletionCheck(
  accessToken: string,
  userId: number,
  signal?: AbortSignal,
): Promise<UserDeletionCheck> {
  const response = await fetch(
    `${API_BASE_URL}/users/${userId}/deletion-check`,
    {
      headers: createHeaders(accessToken),
      signal,
    },
  )

  if (!response.ok) {
    throw new UserApiError(
      await readApiError(response),
      response.status,
    )
  }

  return (await response.json()) as UserDeletionCheck
}

export async function deleteUser(
  accessToken: string,
  userId: number,
  discardUnbilled: boolean,
): Promise<void> {
  const query = discardUnbilled
    ? '?discard_unbilled=true'
    : ''

  const response = await fetch(
    `${API_BASE_URL}/users/${userId}${query}`,
    {
      method: 'DELETE',
      headers: createHeaders(accessToken),
    },
  )

  if (!response.ok) {
    throw new UserApiError(
      await readApiError(response),
      response.status,
    )
  }
}
