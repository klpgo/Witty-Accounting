import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'

import {
  getRetentionOverview,
  purgeRetentionYear,
  SettingsApiError,
  updateRetentionYears,
  type RetentionBlocker,
  type RetentionOverview,
  type RetentionYear,
} from '../api/settings'
import { getAccessToken } from '../auth/tokenStorage'
import { useAuth } from '../auth/useAuth'
import type { MessageKey } from '../i18n/de'
import { useTranslation } from '../i18n/useTranslation'
import { formatUtcDateTime } from '../utils/dateFormat'

const BLOCKER_KEYS: Record<string, MessageKey> = {
  older_year_pending: 'retention.blocker.olderYear',
  draft_cancellations: 'retention.blocker.draftCancellations',
  draft_invoices: 'retention.blocker.draftInvoices',
  unbilled_charging_sessions: 'retention.blocker.unbilledSessions',
  unbilled_base_fees: 'retention.blocker.unbilledFees',
}

/*
 * Aufbewahrungsfrist und Löschen abgelaufener Jahre (Rechnungen, PDFs und
 * Abrechnungsdaten). Gelöscht wird nur auf Anforderung, jahrweise und mit
 * Eingabe der Jahreszahl zur Bestätigung.
 */
function AdminRetentionForm() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const { signOut } = useAuth()

  const [overview, setOverview] = useState<RetentionOverview | null>(null)
  const [retentionYears, setRetentionYears] = useState('')
  const [confirmations, setConfirmations] = useState<Record<number, string>>(
    {},
  )
  const [isLoading, setIsLoading] = useState(true)
  const [isSaving, setIsSaving] = useState(false)
  const [purgingYear, setPurgingYear] = useState<number | null>(null)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)
  const [successMessage, setSuccessMessage] = useState<string | null>(null)

  const handleUnauthorized = useCallback((): void => {
    signOut()
    navigate('/login', { replace: true })
  }, [navigate, signOut])

  const applyOverview = useCallback((loaded: RetentionOverview): void => {
    setOverview(loaded)
    setRetentionYears(String(loaded.retention_years))
    setConfirmations({})
  }, [])

  useEffect(() => {
    const controller = new AbortController()

    async function load(): Promise<void> {
      const accessToken = getAccessToken()

      if (accessToken === null) {
        handleUnauthorized()
        return
      }

      try {
        applyOverview(
          await getRetentionOverview(accessToken, controller.signal),
        )

        // Sprung vom Hinweis auf dem Dashboard
        if (window.location.hash === '#retention') {
          window.requestAnimationFrame(() => {
            document.getElementById('retention')?.scrollIntoView()
          })
        }
      } catch (error) {
        if (error instanceof DOMException && error.name === 'AbortError') {
          return
        }

        if (error instanceof SettingsApiError && error.status === 401) {
          handleUnauthorized()
          return
        }

        setErrorMessage(
          error instanceof Error ? error.message : t('retention.loadFailed'),
        )
      } finally {
        if (!controller.signal.aborted) {
          setIsLoading(false)
        }
      }
    }

    void load()

    return () => {
      controller.abort()
    }
  }, [applyOverview, handleUnauthorized, t])

  function handleError(error: unknown, fallback: string): void {
    if (error instanceof SettingsApiError && error.status === 401) {
      handleUnauthorized()
      return
    }

    setErrorMessage(error instanceof Error ? error.message : fallback)
  }

  async function saveRetentionYears(): Promise<void> {
    const accessToken = getAccessToken()

    if (accessToken === null) {
      handleUnauthorized()
      return
    }

    setIsSaving(true)
    setErrorMessage(null)
    setSuccessMessage(null)

    try {
      const updated = await updateRetentionYears(
        accessToken,
        Number(retentionYears),
      )
      applyOverview(updated)
      setSuccessMessage(
        t('retention.saved', { count: updated.retention_years }),
      )
    } catch (error) {
      handleError(error, t('retention.saveFailed'))
    } finally {
      setIsSaving(false)
    }
  }

  async function purge(entry: RetentionYear): Promise<void> {
    const accessToken = getAccessToken()

    if (accessToken === null) {
      handleUnauthorized()
      return
    }

    setPurgingYear(entry.year)
    setErrorMessage(null)
    setSuccessMessage(null)

    try {
      const result = await purgeRetentionYear(
        accessToken,
        entry.year,
        Number(confirmations[entry.year] ?? ''),
      )

      setSuccessMessage(
        t('retention.purged', {
          year: result.year,
          count: result.invoices + result.cancellations,
        }) +
          (result.pdf_errors.length > 0
            ? ' ' +
              t('retention.pdfErrors', {
                count: result.pdf_errors.length,
              })
            : ''),
      )
      applyOverview(await getRetentionOverview(accessToken))
    } catch (error) {
      handleError(error, t('retention.purgeFailed'))
    } finally {
      setPurgingYear(null)
    }
  }

  function blockerText(blocker: RetentionBlocker): string {
    const key = BLOCKER_KEYS[blocker.code]

    return key === undefined
      ? blocker.message
      : t(key, { count: blocker.count })
  }

  const retentionChanged =
    overview !== null &&
    retentionYears !== String(overview.retention_years)

  return (
    <section className="card settings-form" id="retention">
      <div className="settings-section">
        <div>
          <h2>{t('retention.title')}</h2>
          <p className="muted">{t('retention.intro')}</p>
        </div>

        {errorMessage && (
          <p className="form-error" role="alert">
            {errorMessage}
          </p>
        )}

        {successMessage && (
          <p className="form-success" role="status">
            {successMessage}
          </p>
        )}

        {isLoading || overview === null ? (
          !errorMessage && <p className="muted">{t('common.loading')}</p>
        ) : (
          <>
            <div className="retention-period">
              <label className="form-field">
                {t('retention.years')}
                <input
                  type="number"
                  min={overview.min_retention_years}
                  max={overview.max_retention_years}
                  step={1}
                  value={retentionYears}
                  onChange={(event) => setRetentionYears(event.target.value)}
                />
                <small className="muted">
                  {t('retention.yearsHint', {
                    year: overview.last_purgeable_year,
                  })}
                </small>
              </label>

              <div className="form-actions">
                <button
                  className="button button-secondary"
                  type="button"
                  disabled={!retentionChanged || isSaving}
                  onClick={() => {
                    void saveRetentionYears()
                  }}
                >
                  {isSaving ? t('common.saving') : t('retention.save')}
                </button>
              </div>
            </div>

            <h3>{t('retention.expiredTitle')}</h3>

            {overview.years.length === 0 ? (
              <p className="muted">
                {t('retention.none', { year: overview.last_purgeable_year })}
              </p>
            ) : (
              <>
                <p className="muted">{t('retention.purgeIntro')}</p>

                <div className="table-scroll">
                  <table className="data-table compact-table">
                    <thead>
                      <tr>
                        <th>{t('retention.col.year')}</th>
                        <th className="table-number">
                          {t('retention.col.invoices')}
                        </th>
                        <th className="table-number">
                          {t('retention.col.cancellations')}
                        </th>
                        <th>{t('retention.col.numbers')}</th>
                        <th>{t('retention.col.action')}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {overview.years.map((entry) => {
                        const confirmation = confirmations[entry.year] ?? ''

                        return (
                          <tr key={entry.year}>
                            <td>
                              <strong>{entry.year}</strong>
                            </td>
                            <td className="table-number">{entry.invoices}</td>
                            <td className="table-number">
                              {entry.cancellations}
                            </td>
                            <td>
                              {entry.first_invoice_number ?? '–'}
                              {entry.last_invoice_number &&
                              entry.last_invoice_number !==
                                entry.first_invoice_number
                                ? ` – ${entry.last_invoice_number}`
                                : ''}
                            </td>
                            <td>
                              {entry.purgeable ? (
                                <div className="retention-confirm">
                                  <input
                                    type="text"
                                    inputMode="numeric"
                                    value={confirmation}
                                    placeholder={String(entry.year)}
                                    aria-label={t('retention.confirmLabel', {
                                      year: entry.year,
                                    })}
                                    disabled={purgingYear !== null}
                                    onChange={(event) => {
                                      setConfirmations((current) => ({
                                        ...current,
                                        [entry.year]: event.target.value,
                                      }))
                                    }}
                                  />
                                  <button
                                    className="button button-danger"
                                    type="button"
                                    disabled={
                                      confirmation.trim() !==
                                        String(entry.year) ||
                                      purgingYear !== null
                                    }
                                    onClick={() => {
                                      void purge(entry)
                                    }}
                                  >
                                    {purgingYear === entry.year
                                      ? t('retention.purging')
                                      : t('retention.purge', {
                                          year: entry.year,
                                        })}
                                  </button>
                                </div>
                              ) : (
                                <ul className="retention-blockers">
                                  {entry.blockers.map((blocker) => (
                                    <li key={blocker.code}>
                                      {blockerText(blocker)}
                                    </li>
                                  ))}
                                </ul>
                              )}
                            </td>
                          </tr>
                        )
                      })}
                    </tbody>
                  </table>
                </div>
              </>
            )}

            <h3>{t('retention.protocolTitle')}</h3>

            {overview.protocol.length === 0 ? (
              <p className="muted">{t('retention.protocolEmpty')}</p>
            ) : (
              <div className="table-scroll">
                <table className="data-table compact-table">
                  <thead>
                    <tr>
                      <th>{t('retention.col.purgedAt')}</th>
                      <th>{t('retention.col.year')}</th>
                      <th>{t('retention.col.numbers')}</th>
                      <th className="table-number">
                        {t('retention.col.documents')}
                      </th>
                      <th className="table-number">
                        {t('retention.col.sessions')}
                      </th>
                      <th className="table-number">
                        {t('retention.col.fees')}
                      </th>
                      <th>{t('retention.col.purgedBy')}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {overview.protocol.map((entry) => (
                      <tr key={entry.id}>
                        <td>{formatUtcDateTime(entry.purged_at)}</td>
                        <td>{entry.year}</td>
                        <td>
                          {entry.first_invoice_number ?? '–'}
                          {entry.last_invoice_number &&
                          entry.last_invoice_number !==
                            entry.first_invoice_number
                            ? ` – ${entry.last_invoice_number}`
                            : ''}
                          {entry.pdf_errors.length > 0 && (
                            <span
                              className="retention-warning"
                              title={entry.pdf_errors.join('\n')}
                            >
                              {' '}
                              {t('retention.pdfErrors', {
                                count: entry.pdf_errors.length,
                              })}
                            </span>
                          )}
                        </td>
                        <td className="table-number">
                          {entry.invoices + entry.cancellations}
                        </td>
                        <td className="table-number">
                          {entry.charging_sessions}
                        </td>
                        <td className="table-number">{entry.base_fees}</td>
                        <td>{entry.purged_by ?? '–'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </>
        )}
      </div>
    </section>
  )
}

export default AdminRetentionForm
