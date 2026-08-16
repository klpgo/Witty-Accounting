const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ??
  '/api'

export type DecimalValue = string | number

export interface InvoiceItem {
  id: number
  item_type: string
  monthly_base_fee_charge_id: number | null
  charging_session_id: number | null
  reversed_invoice_item_id: number | null
  rebills_invoice_item_id: number | null
  position_number: number
  description: string
  session_start: string | null
  session_end: string | null
  station_id: string | null
  energy_total_kwh: DecimalValue | null
  energy_grid_kwh: DecimalValue | null
  energy_pv_kwh: DecimalValue | null
  grid_price_net: DecimalValue | null
  pv_price_net: DecimalValue | null
  cost_grid_net: DecimalValue | null
  cost_pv_net: DecimalValue | null
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
  pdf_exported_at: string | null
  pdf_exported_by_user_id: number | null
  pdf_export_remote_path: string | null
  items: InvoiceItem[]
}

export interface InvoiceEmailResponse {
  recipient_email: string
  subject: string
}

export interface InvoiceExportResponse {
  remote_path: string
  exported_at: string
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

export async function sendInvoiceEmail(
  accessToken: string,
  invoiceId: number,
): Promise<InvoiceEmailResponse> {
  const response = await fetch(
    `${API_BASE_URL}/invoices/${invoiceId}/send-email`,
    {
      method: 'POST',
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

  return (
    await response.json()
  ) as InvoiceEmailResponse
}

export async function exportInvoiceSftp(
  accessToken: string,
  invoiceId: number,
): Promise<InvoiceExportResponse> {
  const response = await fetch(
    `${API_BASE_URL}/invoices/${invoiceId}/export-sftp`,
    {
      method: 'POST',
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

  return (
    await response.json()
  ) as InvoiceExportResponse
}

export interface InvoiceDraftCreate {
  user_id: number
  service_period_start: string
  service_period_end: string
}

export async function createInvoiceDraft(
  accessToken: string,
  payload: InvoiceDraftCreate,
): Promise<Invoice> {
  const response = await fetch(
    `${API_BASE_URL}/invoices/drafts`,
    {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${accessToken}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(payload),
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

export interface InvoiceFinalizeRequest {
  issue_date: string
  due_date: string
}

export async function finalizeInvoice(
  accessToken: string,
  invoiceId: number,
  payload: InvoiceFinalizeRequest,
): Promise<Invoice> {
  const response = await fetch(
    `${API_BASE_URL}/invoices/${invoiceId}/finalize`,
    {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${accessToken}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(payload),
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

export interface InvoiceCancellationCreate {
  reason: string
}

export async function createInvoiceCancellation(
  accessToken: string,
  invoiceId: number,
  payload: InvoiceCancellationCreate,
): Promise<Invoice> {
  const response = await fetch(
    `${API_BASE_URL}/invoices/${invoiceId}/cancellations`,
    {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${accessToken}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(payload),
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

export interface InvoiceCancellationFinalize {
  issue_date: string
}

export async function finalizeInvoiceCancellation(
  accessToken: string,
  cancellationId: number,
  payload: InvoiceCancellationFinalize,
): Promise<Invoice> {
  const response = await fetch(
    `${API_BASE_URL}/invoices/${cancellationId}/cancellation/finalize`,
    {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${accessToken}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(payload),
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

export async function deleteInvoiceDraft(
  accessToken: string,
  invoiceId: number,
): Promise<void> {
  const response = await fetch(
    `${API_BASE_URL}/invoices/${invoiceId}`,
    {
      method: 'DELETE',
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
}
