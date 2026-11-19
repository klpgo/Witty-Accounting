import { formatDate } from '../utils/dateFormat'
import { useTranslation } from '../i18n/useTranslation'

/** Erster Tag des Monats, `monthsBack` Monate vor dem aktuellen (YYYY-MM-DD). */
export function monthStartBefore(
  monthsBack: number,
  from: Date = new Date(),
): string {
  const date = new Date(from.getFullYear(), from.getMonth() - monthsBack, 1)
  const month = String(date.getMonth() + 1).padStart(2, '0')

  return `${date.getFullYear()}-${month}-01`
}

/** `value` (YYYY-MM-DD) um `months` Monate früher, immer Monatsanfang. */
function shiftMonths(value: string, months: number): string {
  const year = Number(value.slice(0, 4))
  const month = Number(value.slice(5, 7))

  return monthStartBefore(months, new Date(year, month - 1, 1))
}

interface TimeWindowControlProps {
  /** Beginn des angezeigten Zeitraums (YYYY-MM-DD), null = alles */
  since: string | null
  /** Voreinstellung der Seite, z. B. drei Monate zurück */
  defaultSince: string
  /** Ältestes vorhandenes Datum (YYYY-MM-DD oder ISO), null = nichts da */
  oldest: string | null
  /** Schrittweite für „Ältere laden“ */
  stepMonths: number
  /** Text der Voreinstellung, z. B. „Letzte 3 Monate“ */
  defaultLabel: string
  /** Hinweis, was unabhängig vom Zeitraum immer angezeigt wird */
  alwaysShownHint: string
  disabled?: boolean
  onChange: (since: string | null) => void
}

/*
 * Auswahl des angezeigten Zeitraums für lange Listen (Ladevorgänge,
 * Rechnungen): Voreinstellung, ganze Jahre, alles – und „Ältere laden“.
 */
function TimeWindowControl({
  since,
  defaultSince,
  oldest,
  stepMonths,
  defaultLabel,
  alwaysShownHint,
  disabled = false,
  onChange,
}: TimeWindowControlProps) {
  const { t } = useTranslation()

  const oldestDay = oldest === null ? null : oldest.slice(0, 10)
  const hasOlder =
    since !== null && oldestDay !== null && oldestDay < since

  const options: { value: string; label: string }[] = [
    { value: defaultSince, label: defaultLabel },
  ]

  if (oldestDay !== null) {
    const currentYear = new Date().getFullYear()
    const oldestYear = Number(oldestDay.slice(0, 4))

    for (let year = currentYear; year >= oldestYear; year -= 1) {
      const value = `${year}-01-01`

      if (value !== defaultSince) {
        options.push({
          value,
          label: t('timeWindow.sinceYear', { year: String(year) }),
        })
      }
    }
  }

  if (since !== null && !options.some((option) => option.value === since)) {
    options.push({
      value: since,
      label: t('timeWindow.sinceDate', { date: formatDate(since) }),
    })
  }

  options.push({ value: 'all', label: t('timeWindow.all') })

  return (
    <div className="time-window">
      <label className="time-window-select">
        <span>{t('timeWindow.label')}</span>
        <select
          value={since ?? 'all'}
          disabled={disabled}
          onChange={(event) =>
            onChange(
              event.target.value === 'all' ? null : event.target.value,
            )
          }
        >
          {options.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </label>

      {hasOlder && (
        <button
          className="button button-secondary"
          type="button"
          disabled={disabled}
          onClick={() => {
            if (since !== null) {
              onChange(shiftMonths(since, stepMonths))
            }
          }}
        >
          {t('timeWindow.loadOlder', { count: stepMonths })}
        </button>
      )}

      <p className="muted time-window-hint">
        {since === null
          ? t('timeWindow.showingAll')
          : t('timeWindow.showingSince', { date: formatDate(since) })}{' '}
        {alwaysShownHint}
      </p>
    </div>
  )
}

export default TimeWindowControl
