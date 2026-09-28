/*
 * Zahlen und Beträge im Gebietsschema der Instanz. Gebietsschema und
 * Währung kommen aus den öffentlichen Einstellungen (setNumberFormat).
 */
let numberLocale = 'de-DE'
let defaultCurrency = 'EUR'

export function setNumberFormat(locale: string, currency: string): void {
  try {
    // prüft, ob der Browser beides kennt
    new Intl.NumberFormat(locale, { style: 'currency', currency })
    numberLocale = locale
    defaultCurrency = currency
  } catch {
    // unbekannt: bisherige Werte beibehalten
  }
}

export function getDefaultCurrency(): string {
  return defaultCurrency
}

function toNumber(value: string | number | null | undefined): number | null {
  if (value === null || value === undefined || value === '') {
    return null
  }

  const numericValue = Number(value)

  return Number.isFinite(numericValue) ? numericValue : null
}

/** Zahl mit bis zu `maximumFractionDigits` Nachkommastellen: 1.234,567 */
export function formatNumber(
  value: string | number | null | undefined,
  maximumFractionDigits = 3,
): string {
  const numericValue = toNumber(value)

  if (numericValue === null) {
    return '–'
  }

  return new Intl.NumberFormat(numberLocale, {
    minimumFractionDigits: 0,
    maximumFractionDigits,
  }).format(numericValue)
}

/** Betrag in der angegebenen oder der Standardwährung: 1.234,56 € */
export function formatCurrency(
  value: string | number | null | undefined,
  currency: string = defaultCurrency,
): string {
  const numericValue = toNumber(value)

  if (numericValue === null) {
    return '–'
  }

  return new Intl.NumberFormat(numberLocale, {
    style: 'currency',
    currency,
  }).format(numericValue)
}
