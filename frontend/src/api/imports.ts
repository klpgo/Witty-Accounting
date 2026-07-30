const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ??
  'http://localhost:8000'

export interface ImportResult {
  read: number
  imported: number
  skipped: number
  unknown_rfid_sessions: number
  unknown_rfid_numbers: string[]
  priced: number
  missing_price: number
  invalid_energy: number
}

interface ApiErrorResponse {
  detail?: string
}

export class ImportApiError extends Error {
  status: number

  constructor(
    message: string,
    status: number,
  ) {
    super(message)

    this.name = 'ImportApiError'
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

export async function uploadXlsx(
  accessToken: string,
  file: File,
  signal?: AbortSignal,
): Promise<ImportResult> {
  const formData = new FormData()

  formData.append(
    'file',
    file,
    file.name,
  )

  const response = await fetch(
    `${API_BASE_URL}/imports/xlsx`,
    {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${accessToken}`,
      },
      body: formData,
      signal,
    },
  )

  if (!response.ok) {
    throw new ImportApiError(
      await getErrorMessage(response),
      response.status,
    )
  }

  return (await response.json()) as ImportResult
}
