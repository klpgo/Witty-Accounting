import { readApiError } from './errors'

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ??
  '/api'

export type ServerStatus =
  | 'online'
  | 'maintenance'

export interface DashboardData {
  server_status: ServerStatus
  admin_note: string | null
  latest_charging_session_at: string | null
  invoiced_through: string | null
  backend_version: string
}

export class DashboardApiError extends Error {
  readonly status: number

  constructor(
    message: string,
    status: number,
  ) {
    super(message)
    this.name = 'DashboardApiError'
    this.status = status
  }
}

export async function getDashboard(
  accessToken: string,
  signal?: AbortSignal,
): Promise<DashboardData> {
  const response = await fetch(
    `${API_BASE_URL}/dashboard`,
    {
      headers: {
        Authorization: `Bearer ${accessToken}`,
      },
      signal,
    },
  )

  if (!response.ok) {
    throw new DashboardApiError(
      await readApiError(response),
      response.status,
    )
  }

  return (
    await response.json()
  ) as DashboardData
}
