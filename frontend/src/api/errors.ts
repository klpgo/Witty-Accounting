import { de, type MessageKey } from '../i18n/de'
import {
  type Language,
  type MessageParams,
  translate,
} from '../i18n/translate'

/*
 * Fehlermeldungen des Backends.
 *
 * Das Backend liefert zu jeder bekannten Meldung einen Code mit Parametern
 * (siehe backend/app/errors.py). Der Text kommt aus den Sprachdateien
 * (apiError.<code>). Nur wenn kein Code passt, wird detail angezeigt.
 */

type ApiErrorParam =
  | string
  | number
  | ApiErrorDescriptor
  | ApiErrorDescriptor[]

export interface ApiErrorDescriptor {
  code: string
  params?: Record<string, ApiErrorParam>
}

interface ApiErrorBody {
  detail?: unknown
  code?: unknown
  params?: unknown
}

// Sprache der Oberfläche; wird vom I18nProvider gesetzt
let currentLanguage: Language = 'de'

export function setApiErrorLanguage(language: Language): void {
  currentLanguage = language
}

function isDescriptor(value: unknown): value is ApiErrorDescriptor {
  return (
    typeof value === 'object' &&
    value !== null &&
    typeof (value as ApiErrorDescriptor).code === 'string'
  )
}

function messageKey(code: string): MessageKey | null {
  const key = `apiError.${code}`

  return key in de ? (key as MessageKey) : null
}

// Aufzählungen ohne "und" (z. B. "3 neu, 2 übersprungen")
const UNIT_LIST_PARAMS = new Set(['parts'])

const ISO_DATE = /^(\d{4})-(\d{2})-(\d{2})$/

function formatParam(
  name: string,
  value: ApiErrorParam,
  language: Language,
): string {
  if (Array.isArray(value)) {
    return new Intl.ListFormat(language, {
      style: 'long',
      type: UNIT_LIST_PARAMS.has(name) ? 'unit' : 'conjunction',
    }).format(value.map((item) => formatParam(name, item, language)))
  }

  if (isDescriptor(value)) {
    return translateApiError(value, language) ?? value.code
  }

  const date = typeof value === 'string' ? ISO_DATE.exec(value) : null

  if (date) {
    return new Intl.DateTimeFormat(language, {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      timeZone: 'UTC',
    }).format(
      new Date(Date.UTC(Number(date[1]), Number(date[2]) - 1, Number(date[3]))),
    )
  }

  return String(value)
}

/* Text zu einem Code; null, wenn die Oberfläche den Code nicht kennt. */
export function translateApiError(
  descriptor: ApiErrorDescriptor,
  language: Language = currentLanguage,
): string | null {
  const key = messageKey(descriptor.code)

  if (key === null) {
    return null
  }

  const params: MessageParams = {}

  for (const [name, value] of Object.entries(descriptor.params ?? {})) {
    params[name] = formatParam(name, value, language)
  }

  return translate(language, key, params)
}

function validationMessage(item: unknown): string | null {
  if (isDescriptor(item)) {
    const text = translateApiError(item)

    if (text !== null) {
      return text
    }
  }

  if (
    typeof item === 'object' &&
    item !== null &&
    typeof (item as { msg?: unknown }).msg === 'string'
  ) {
    return (item as { msg: string }).msg
  }

  return null
}

/* Gespeicherte Meldung (Status, letzter Fehler) in der Sprache der Oberfläche. */
export function localizeMessage(
  message: string | null,
  code: ApiErrorDescriptor | null | undefined,
): string | null {
  if (code) {
    const text = translateApiError(code)

    if (text !== null) {
      return text
    }
  }

  return message
}

/* Liest die Fehlermeldung aus einer Antwort des Backends. */
export async function readApiError(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as ApiErrorBody

    if (typeof body.code === 'string') {
      const text = translateApiError(body as ApiErrorDescriptor)

      if (text !== null) {
        return text
      }
    }

    if (typeof body.detail === 'string' && body.detail !== '') {
      return body.detail
    }

    if (Array.isArray(body.detail)) {
      const messages = body.detail
        .map(validationMessage)
        .filter((message): message is string => message !== null)

      if (messages.length > 0) {
        return messages.join(' ')
      }
    }
  } catch {
    // Die Antwort enthielt kein JSON.
  }

  return translate(currentLanguage, 'apiError.requestFailed', {
    status: response.status,
  })
}
