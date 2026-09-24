const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ??
  '/api'

export interface ImportResult {
  read: number
  imported: number
  skipped: number
  unknown_rfid_sessions: number
  unknown_rfid_numbers: string[]
  priced: number
  missing_price: number
  invalid_energy: number
  unknown_rfid_cards?: string[]
  inactive_rfid_cards?: string[]
  unassigned_rfid_numbers?: string[]
  backfilled_rfid_numbers?: number
  reassigned_sessions?: number
  fetched_from?: string | null
}

interface ValidationErrorDetail {
  msg?: string
}

interface ApiErrorResponse {
  detail?: string | ValidationErrorDetail[]
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

    if (typeof body.detail === 'string') {
      return body.detail
    }

    if (Array.isArray(body.detail)) {
      const messages = body.detail
        .map((detail) => detail.msg)
        .filter(
          (message): message is string =>
            typeof message === 'string',
        )

      if (messages.length > 0) {
        return messages.join(' ')
      }
    }
  } catch {
    // Die Antwort enthielt kein JSON.
  }

  return `Anfrage fehlgeschlagen (${response.status}).`
}

export type ImportFileType = 'xlsx' | 'json'

export function getImportFileType(
  fileName: string,
): ImportFileType | null {
  const normalizedName = fileName.toLowerCase()

  if (normalizedName.endsWith('.xlsx')) {
    return 'xlsx'
  }

  if (normalizedName.endsWith('.json')) {
    return 'json'
  }

  return null
}

export async function uploadImportFile(
  accessToken: string,
  file: File,
  signal?: AbortSignal,
): Promise<ImportResult> {
  const fileType = getImportFileType(file.name)

  if (fileType === null) {
    throw new ImportApiError(
      'Es werden nur XLSX- und JSON-Dateien unterstützt.',
      400,
    )
  }

  return uploadFile(
    accessToken,
    file,
    fileType,
    signal,
  )
}

export async function uploadXlsx(
  accessToken: string,
  file: File,
  signal?: AbortSignal,
): Promise<ImportResult> {
  return uploadFile(
    accessToken,
    file,
    'xlsx',
    signal,
  )
}

async function uploadFile(
  accessToken: string,
  file: File,
  fileType: ImportFileType,
  signal?: AbortSignal,
): Promise<ImportResult> {
  const formData = new FormData()

  formData.append(
    'file',
    file,
    file.name,
  )

  const response = await fetch(
    `${API_BASE_URL}/imports/${fileType}`,
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

export interface HagerImportRequest {
  date_from?: string
  date_to?: string
  fetch_all?: boolean
}

export async function importFromHager(
  accessToken: string,
  payload: HagerImportRequest = {},
  signal?: AbortSignal,
): Promise<ImportResult> {
  const response = await fetch(
    `${API_BASE_URL}/imports/hager`,
    {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${accessToken}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(payload),
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
