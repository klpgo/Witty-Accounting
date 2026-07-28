const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ??
  'http://localhost:8000'

export type DecimalValue = string | number

export interface InvoiceItem {
  id: number
  charging_session_id: number | null
  reversed_invoice_item_id: number | null
  rebills_invoice_item_id: number | null
  position_number: number
  description: string
  session_start: string
  session_end: string
  station_id: string
  energy_total_kwh: DecimalValue
  energy_grid_kwh: DecimalValue
  energy_pv_kwh: DecimalValue
  grid_price_net: DecimalValue
  pv_price_net: DecimalValue
  cost_grid_net: DecimalValue
  cost_pv_net: DecimalValue
  net_amount: DecimalValue
  vat_rate: DecimalValue
  vat_amount: DecimalValue
  gross_amount: DecimalValue
}

export interface Invoice {
  id: number
  invoice_number: string | null
  document_type: string
  original_invoice_id: number | null
  cancellation_reason: string | null
  cancelled_at: string | null
  user_id: number
  recipient_name: string
  recipient_address: string
  status: string
  issue_date: string | null
  due_date: string | null
  service_period_start: string
  service_period_end: string
  currency: string
  total_net: DecimalValue
  vat_amount: DecimalValue
  total_gross: DecimalValue
  created_at: string
  updated_at: string
  finalized_at: string | null
  pdf_storage_path: string | null
  pdf_sha256: string | null
  pdf_size_bytes: number | null
  pdf_created_at: string | null
  items: InvoiceItem[]
}

interface ApiErrorResponse {
  detail?: string
}

export class InvoiceApiError extends Error {
  readonly status: number

  constructor(
    message: string,
    status: number,
  ) {
    super(message)
    this.name = 'InvoiceApiError'
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

export async function listInvoices(
  accessToken: string,
  signal?: AbortSignal,
): Promise<Invoice[]> {
  const response = await fetch(
    `${API_BASE_URL}/invoices`,
    {
      headers: {
        Authorization: `Bearer ${accessToken}`,
      },
      signal,
    },
  )

  if (!response.ok) {
    throw new InvoiceApiError(
      await getErrorMessage(response),
      response.status,
    )
  }

  return (await response.json()) as Invoice[]
}

export async function getInvoice(
  accessToken: string,
  invoiceId: number,
  signal?: AbortSignal,
): Promise<Invoice> {
  const response = await fetch(
    `${API_BASE_URL}/invoices/${invoiceId}`,
    {
      headers: {
        Authorization: `Bearer ${accessToken}`,
      },
      signal,
    },
  )

  if (!response.ok) {
    throw new InvoiceApiError(
      await getErrorMessage(response),
      response.status,
    )
  }

  return (await response.json()) as Invoice
}

export async function downloadInvoicePdf(
  accessToken: string,
  invoiceId: number,
): Promise<Blob> {
  const response = await fetch(
    `${API_BASE_URL}/invoices/${invoiceId}/pdf`,
    {
      headers: {
        Authorization: `Bearer ${accessToken}`,
      },
    },
  )

  if (!response.ok) {
    throw new InvoiceApiError(
      await getErrorMessage(response),
      response.status,
    )
  }

  return response.blob()
}
