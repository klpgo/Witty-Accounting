const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ??
  '/api'

export interface RFIDCard {
  id: number
  rfid_number: string
  description: string | null
  active: boolean
  created_at: string
  updated_at: string
}

export interface RFIDCardAssignment {
  id: number
  rfid_card_id: number
  user_id: number
  valid_from: string
  valid_to: string | null
  created_at: string
  updated_at: string
}

export interface RFIDCardCreate {
  rfid_number: string
  description?: string | null
  active?: boolean
}

export interface RFIDCardUpdate {
  rfid_number?: string
  description?: string | null
  active?: boolean
}

export interface RFIDCardAssignmentCreate {
  user_id: number
  valid_from: string
  valid_to?: string | null
}

export interface RFIDCardAssignmentUpdate {
  user_id?: number
  valid_from?: string
  valid_to?: string | null
}

interface ApiErrorResponse {
  detail?: string
}

export class RFIDCardApiError extends Error {
  readonly status: number

  constructor(
    message: string,
    status: number,
  ) {
    super(message)
    this.name = 'RFIDCardApiError'
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

async function requireSuccess(
  response: Response,
): Promise<void> {
  if (!response.ok) {
    throw new RFIDCardApiError(
      await getErrorMessage(response),
      response.status,
    )
  }
}

export async function listRFIDCards(
  accessToken: string,
  signal?: AbortSignal,
): Promise<RFIDCard[]> {
  const response = await fetch(
    `${API_BASE_URL}/rfid-cards`,
    {
      headers: createHeaders(accessToken),
      signal,
    },
  )

  await requireSuccess(response)

  return (await response.json()) as RFIDCard[]
}

export async function createRFIDCard(
  accessToken: string,
  payload: RFIDCardCreate,
): Promise<RFIDCard> {
  const response = await fetch(
    `${API_BASE_URL}/rfid-cards`,
    {
      method: 'POST',
      headers: createHeaders(
        accessToken,
        true,
      ),
      body: JSON.stringify(payload),
    },
  )

  await requireSuccess(response)

  return (await response.json()) as RFIDCard
}

export async function updateRFIDCard(
  accessToken: string,
  cardId: number,
  payload: RFIDCardUpdate,
): Promise<RFIDCard> {
  const response = await fetch(
    `${API_BASE_URL}/rfid-cards/${cardId}`,
    {
      method: 'PATCH',
      headers: createHeaders(
        accessToken,
        true,
      ),
      body: JSON.stringify(payload),
    },
  )

  await requireSuccess(response)

  return (await response.json()) as RFIDCard
}

export async function listRFIDCardAssignments(
  accessToken: string,
  cardId: number,
  signal?: AbortSignal,
): Promise<RFIDCardAssignment[]> {
  const response = await fetch(
    `${API_BASE_URL}/rfid-cards/${cardId}/assignments`,
    {
      headers: createHeaders(accessToken),
      signal,
    },
  )

  await requireSuccess(response)

  return (
    await response.json()
  ) as RFIDCardAssignment[]
}

export async function createRFIDCardAssignment(
  accessToken: string,
  cardId: number,
  payload: RFIDCardAssignmentCreate,
): Promise<RFIDCardAssignment> {
  const response = await fetch(
    `${API_BASE_URL}/rfid-cards/${cardId}/assignments`,
    {
      method: 'POST',
      headers: createHeaders(
        accessToken,
        true,
      ),
      body: JSON.stringify(payload),
    },
  )

  await requireSuccess(response)

  return (
    await response.json()
  ) as RFIDCardAssignment
}

export async function updateRFIDCardAssignment(
  accessToken: string,
  assignmentId: number,
  payload: RFIDCardAssignmentUpdate,
): Promise<RFIDCardAssignment> {
  const response = await fetch(
    `${API_BASE_URL}/rfid-card-assignments/${assignmentId}`,
    {
      method: 'PATCH',
      headers: createHeaders(
        accessToken,
        true,
      ),
      body: JSON.stringify(payload),
    },
  )

  await requireSuccess(response)

  return (
    await response.json()
  ) as RFIDCardAssignment
}
