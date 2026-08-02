const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ??
  'http://localhost:8000'

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

interface ApiErrorResponse {
  detail?: string
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

async function getErrorMessage(
  response: Response,
): Promise<string> {
  try {
    const body =
      (await response.json()) as ApiErrorResponse

    if (typeof body.detail === 'string') {
      return body.detail
    }
  } catch {
    // Die Antwort enthielt kein JSON.
  }

  return `Anfrage fehlgeschlagen (${response.status}).`
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
      await getErrorMessage(response),
      response.status,
    )
  }

  return (
    await response.json()
  ) as DashboardData
}
