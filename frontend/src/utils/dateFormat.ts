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

// Gebietsschema und Zeitzone der Instanz, gesetzt aus den öffentlichen
// Einstellungen beim Start der Anwendung (vor dem ersten Rendern)
let displayLocale = 'de-DE'
let displayTimeZone = 'Europe/Berlin'

const DATE_OPTIONS: Intl.DateTimeFormatOptions = {
  day: '2-digit',
  month: '2-digit',
  year: 'numeric',
}

const DATE_TIME_OPTIONS: Intl.DateTimeFormatOptions = {
  ...DATE_OPTIONS,
  hour: '2-digit',
  minute: '2-digit',
}

let dateFormat = new Intl.DateTimeFormat(displayLocale, DATE_OPTIONS)
let dateTimeFormat = new Intl.DateTimeFormat(displayLocale, DATE_TIME_OPTIONS)
let timeFormat = new Intl.DateTimeFormat(displayLocale, {
  hour: '2-digit',
  minute: '2-digit',
})
let shortDateTimeFormat = new Intl.DateTimeFormat(displayLocale, {
  day: '2-digit',
  month: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
})
let utcDateTimeFormat = new Intl.DateTimeFormat(displayLocale, {
  ...DATE_TIME_OPTIONS,
  timeZone: displayTimeZone,
})

function rebuildFormats(locale: string, timeZone: string): void {
  dateFormat = new Intl.DateTimeFormat(locale, DATE_OPTIONS)
  dateTimeFormat = new Intl.DateTimeFormat(locale, DATE_TIME_OPTIONS)
  timeFormat = new Intl.DateTimeFormat(locale, {
    hour: '2-digit',
    minute: '2-digit',
  })
  shortDateTimeFormat = new Intl.DateTimeFormat(locale, {
    day: '2-digit',
    month: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
  utcDateTimeFormat = new Intl.DateTimeFormat(locale, {
    ...DATE_TIME_OPTIONS,
    timeZone,
  })
  displayLocale = locale
  displayTimeZone = timeZone
}

export function setDisplayLocale(locale: string): void {
  try {
    rebuildFormats(locale, displayTimeZone)
  } catch {
    // unbekanntes Gebietsschema im Browser: bisheriges beibehalten
  }
}

export function getDisplayLocale(): string {
  return displayLocale
}

export function setDisplayTimeZone(timeZone: string): void {
  try {
    rebuildFormats(displayLocale, timeZone)
  } catch {
    // unbekannte Zone im Browser: bisherige beibehalten
  }
}

export function getDisplayTimeZone(): string {
  return displayTimeZone
}

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

  return Number.isNaN(date.getTime()) ? value : dateFormat.format(date)
}

/** Ortszeit ohne Zeitzone: 01.07.2026, 07:45 */
export function formatLocalDateTime(value: string | null): string {
  if (value === null) {
    return '–'
  }

  const date = parseLocal(value)

  return Number.isNaN(date.getTime())
    ? value
    : dateTimeFormat.format(date)
}

/** UTC-Zeitstempel der API in der Zeitzone der Instanz: 25.09.2026, 10:27 */
export function formatUtcDateTime(value: string | null): string {
  if (value === null) {
    return '–'
  }

  const date = new Date(HAS_TIME_ZONE.test(value) ? value : `${value}Z`)

  return Number.isNaN(date.getTime())
    ? value
    : utcDateTimeFormat.format(date)
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

  return `${dateFormat.format(startDate)} – ${dateFormat.format(lastDay)}`
}

/** Uhrzeit: 14:23 */
export function formatTime(date: Date): string {
  return timeFormat.format(date)
}

/** Tag, Monat und Uhrzeit ohne Jahr: 13.08., 06:10 */
export function formatShortDateTime(date: Date): string {
  return shortDateTimeFormat.format(date)
}

/** Kalenderdatum aus einem Date-Objekt: 12.08.2026 */
export function formatDateValue(date: Date): string {
  return dateFormat.format(date)
}
