const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ??
  '/api'

export interface PublicSettings {
  app_name: string
}

export interface GlobalSettings {
  app_name: string
  maintenance_mode: boolean
  dashboard_note: string | null
  monthly_base_fee_net: string
  monthly_base_fee_vat_rate: string
  invoice_payment_term_days: number
  invoice_issuer_name: string | null
  invoice_issuer_address: string | null
  invoice_tax_number: string | null
  invoice_vat_id: string | null
  invoice_bank_name: string | null
  invoice_iban: string | null
  invoice_bic: string | null
  invoice_number_prefix: string
  invoice_pdf_format: 'standard' | 'pdfa-2b'
  password_min_length: number
  password_require_uppercase: boolean
  password_require_lowercase: boolean
  password_require_digit: boolean
  password_require_special: boolean
  frontend_base_url: string
  password_reset_token_expire_minutes: number
}

export interface GlobalSettingsUpdate {
  app_name?: string
  maintenance_mode?: boolean
  dashboard_note?: string | null
  monthly_base_fee_net?: string
  monthly_base_fee_vat_rate?: string
  invoice_payment_term_days?: number
  invoice_issuer_name?: string | null
  invoice_issuer_address?: string | null
  invoice_tax_number?: string | null
  invoice_vat_id?: string | null
  invoice_bank_name?: string | null
  invoice_iban?: string | null
  invoice_bic?: string | null
  invoice_number_prefix?: string
  invoice_pdf_format?: 'standard' | 'pdfa-2b'
  password_min_length?: number
  password_require_uppercase?: boolean
  password_require_lowercase?: boolean
  password_require_digit?: boolean
  password_require_special?: boolean
  frontend_base_url?: string
  password_reset_token_expire_minutes?: number
}

export interface SmtpSettings {
  smtp_use_database_settings: boolean
  mail_sending_enabled: boolean
  smtp_host: string
  smtp_port: number
  smtp_timeout_seconds: string
  smtp_starttls: boolean
  smtp_username: string | null
  smtp_password_configured: boolean
  mail_from_address: string
  mail_from_name: string
}

export interface SmtpSettingsUpdate {
  smtp_use_database_settings?: boolean
  mail_sending_enabled?: boolean
  smtp_host?: string
  smtp_port?: number
  smtp_timeout_seconds?: string
  smtp_starttls?: boolean
  smtp_username?: string | null
  smtp_password?: string
  clear_smtp_password?: boolean
  mail_from_address?: string
  mail_from_name?: string
}

export interface SmtpTestEmailResponse {
  recipient_email: string
  subject: string
}

export interface EnergyPrice {
  id: number
  valid_from: string
  grid_price_net: string
  pv_price_net: string
  vat_rate: string
  created_at: string
  updated_at: string
}

export interface CurrentEnergyPriceUpdate {
  grid_price_net: string
  pv_price_net: string
  vat_rate: string
}

interface ValidationErrorDetail {
  msg?: string
}

interface ApiErrorResponse {
  detail?: string | ValidationErrorDetail[]
}

export class SettingsApiError extends Error {
  readonly status: number

  constructor(
    message: string,
    status: number,
  ) {
    super(message)
    this.name = 'SettingsApiError'
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

export async function getPublicSettings():
Promise<PublicSettings> {
  const response = await fetch(
    `${API_BASE_URL}/settings/public`,
  )

  if (!response.ok) {
    throw new SettingsApiError(
      await getErrorMessage(response),
      response.status,
    )
  }

  return (
    await response.json()
  ) as PublicSettings
}

export async function getGlobalSettings(
  accessToken: string,
  signal?: AbortSignal,
): Promise<GlobalSettings> {
  const response = await fetch(
    `${API_BASE_URL}/settings`,
    {
      headers: createHeaders(accessToken),
      signal,
    },
  )

  if (!response.ok) {
    throw new SettingsApiError(
      await getErrorMessage(response),
      response.status,
    )
  }

  return (
    await response.json()
  ) as GlobalSettings
}

export async function getSmtpSettings(
  accessToken: string,
  signal?: AbortSignal,
): Promise<SmtpSettings> {
  const response = await fetch(
    `${API_BASE_URL}/settings/smtp`,
    {
      headers: createHeaders(accessToken),
      signal,
    },
  )

  if (!response.ok) {
    throw new SettingsApiError(
      await getErrorMessage(response),
      response.status,
    )
  }

  return (
    await response.json()
  ) as SmtpSettings
}

export async function updateSmtpSettings(
  accessToken: string,
  payload: SmtpSettingsUpdate,
): Promise<SmtpSettings> {
  const response = await fetch(
    `${API_BASE_URL}/settings/smtp`,
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
    throw new SettingsApiError(
      await getErrorMessage(response),
      response.status,
    )
  }

  return (
    await response.json()
  ) as SmtpSettings
}

export async function testSmtpSettings(
  accessToken: string,
): Promise<SmtpTestEmailResponse> {
  const response = await fetch(
    `${API_BASE_URL}/settings/smtp/test`,
    {
      method: 'POST',
      headers: createHeaders(accessToken),
    },
  )

  if (!response.ok) {
    throw new SettingsApiError(
      await getErrorMessage(response),
      response.status,
    )
  }

  return (
    await response.json()
  ) as SmtpTestEmailResponse
}

export async function updateGlobalSettings(
  accessToken: string,
  payload: GlobalSettingsUpdate,
): Promise<GlobalSettings> {
  const response = await fetch(
    `${API_BASE_URL}/settings`,
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
    throw new SettingsApiError(
      await getErrorMessage(response),
      response.status,
    )
  }

  return (
    await response.json()
  ) as GlobalSettings
}

export async function getCurrentEnergyPrice(
  accessToken: string,
  signal?: AbortSignal,
): Promise<EnergyPrice> {
  const response = await fetch(
    `${API_BASE_URL}/energy-prices/current`,
    {
      headers: createHeaders(accessToken),
      signal,
    },
  )

  if (!response.ok) {
    throw new SettingsApiError(
      await getErrorMessage(response),
      response.status,
    )
  }

  return (
    await response.json()
  ) as EnergyPrice
}

export async function updateCurrentEnergyPrice(
  accessToken: string,
  payload: CurrentEnergyPriceUpdate,
): Promise<EnergyPrice> {
  const response = await fetch(
    `${API_BASE_URL}/energy-prices/current`,
    {
      method: 'PUT',
      headers: createHeaders(
        accessToken,
        true,
      ),
      body: JSON.stringify(payload),
    },
  )

  if (!response.ok) {
    throw new SettingsApiError(
      await getErrorMessage(response),
      response.status,
    )
  }

  return (
    await response.json()
  ) as EnergyPrice
}
