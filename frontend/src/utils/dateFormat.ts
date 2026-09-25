/*
 * Einheitliche Datumsformate für Witty.
 *
 * Zeitbasis der API:
 * - Kalenderdaten (Rechnungsdatum, Fälligkeit): "2026-09-25"
 * - Ortszeit ohne Zeitzone (Ladevorgänge, Leistungszeitraum):
 *   "2026-07-01T07:45:00" – wird unverändert angezeigt
 * - technische Zeitstempel (Erstellt, Export): UTC ohne Zeitzone,
 *   "2026-09-25T08:27:00" – muss als UTC gelesen werden
 */

const DATE_FORMAT = new Intl.DateTimeFormat('de-DE', {
  day: '2-digit',
  month: '2-digit',
  year: 'numeric',
})

const DATE_TIME_FORMAT = new Intl.DateTimeFormat('de-DE', {
  day: '2-digit',
  month: '2-digit',
  year: 'numeric',
  hour: '2-digit',
  minute: '2-digit',
})

const DATE_TIME_FORMAT_BERLIN = new Intl.DateTimeFormat('de-DE', {
  day: '2-digit',
  month: '2-digit',
  year: 'numeric',
  hour: '2-digit',
  minute: '2-digit',
  timeZone: 'Europe/Berlin',
})

const HAS_TIME_ZONE = /(Z|[+-]\d{2}:?\d{2})$/

function parseLocal(value: string): Date {
  // "2026-09-25" ohne Uhrzeit würde sonst als UTC gelesen
  return new Date(value.length === 10 ? `${value}T00:00:00` : value)
}

/** Kalenderdatum: 25.09.2026 */
export function formatDate(value: string | null): string {
  if (value === null) {
    return '–'
  }

  const date = parseLocal(value)

  return Number.isNaN(date.getTime()) ? value : DATE_FORMAT.format(date)
}

/** Ortszeit ohne Zeitzone: 01.07.2026, 07:45 */
export function formatLocalDateTime(value: string | null): string {
  if (value === null) {
    return '–'
  }

  const date = parseLocal(value)

  return Number.isNaN(date.getTime())
    ? value
    : DATE_TIME_FORMAT.format(date)
}

/** UTC-Zeitstempel der API in deutscher Zeit: 25.09.2026, 10:27 */
export function formatUtcDateTime(value: string | null): string {
  if (value === null) {
    return '–'
  }

  const date = new Date(HAS_TIME_ZONE.test(value) ? value : `${value}Z`)

  return Number.isNaN(date.getTime())
    ? value
    : DATE_TIME_FORMAT_BERLIN.format(date)
}

/**
 * Leistungszeitraum mit letztem Leistungstag. Das gespeicherte Ende
 * ist exklusiv (01.08.2026 00:00 für den Monat Juli):
 * "01.07.2026 – 31.07.2026".
 */
export function formatServicePeriod(
  start: string | null,
  end: string | null,
): string {
  if (start === null || end === null) {
    return '–'
  }

  const startDate = parseLocal(start)
  const endDate = parseLocal(end)

  if (
    Number.isNaN(startDate.getTime()) ||
    Number.isNaN(endDate.getTime())
  ) {
    return `${start} – ${end}`
  }

  const endsAtMidnight =
    endDate.getHours() === 0 &&
    endDate.getMinutes() === 0 &&
    endDate.getSeconds() === 0

  const lastDay = new Date(endDate)

  if (endsAtMidnight && endDate > startDate) {
    lastDay.setDate(lastDay.getDate() - 1)
  }

  return `${DATE_FORMAT.format(startDate)} – ${DATE_FORMAT.format(lastDay)}`
}
