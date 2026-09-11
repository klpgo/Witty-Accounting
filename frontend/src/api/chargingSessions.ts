const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ??
  '/api'

export type DecimalValue = string | number

export interface ChargingSession {
  id: number
  user_id: number | null
  user_name: string | null
  rfid_number: string | null
  station_id: string
  start_time: string
  end_time: string
  energy_total_kwh: number
  energy_pv_kwh: number
  cost_grid_net: DecimalValue | null
  cost_pv_net: DecimalValue | null
  vat_rate: DecimalValue | null
  invoiced: boolean
  invoice_id: number | null
  invoice_number: string | null
  invoice_status: string | null
}

interface ApiErrorResponse {
  detail?: string
}

export class ChargingSessionApiError extends Error {
  readonly status: number

  constructor(
    message: string,
    status: number,
  ) {
    super(message)
    this.name = 'ChargingSessionApiError'
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

export async function listChargingSessions(
  accessToken: string,
  signal?: AbortSignal,
): Promise<ChargingSession[]> {
  const response = await fetch(
    `${API_BASE_URL}/charging-sessions`,
    {
      headers: {
        Authorization: `Bearer ${accessToken}`,
      },
      signal,
    },
  )

  if (!response.ok) {
    throw new ChargingSessionApiError(
      await getErrorMessage(response),
      response.status,
    )
  }

  return (
    await response.json()
  ) as ChargingSession[]
}
