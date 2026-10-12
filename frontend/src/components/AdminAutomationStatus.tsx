import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

import {
  getAutoBillingSettings,
  getHagerSettings,
  type AutoBillingSettings,
  type BillingRun,
  type HagerAutoImportStatus,
  type HagerSettings,
} from '../api/settings'
import { getAccessToken } from '../auth/tokenStorage'
import type { MessageKey } from '../i18n/de'
import { useTranslation } from '../i18n/useTranslation'
import {
  formatDate,
  formatServicePeriod,
  formatUtcDateTime,
} from '../utils/dateFormat'

const IMPORT_STATUS_KEYS: Record<HagerAutoImportStatus, MessageKey> = {
  running: 'settings.autoImport.status.running',
  success: 'settings.autoImport.status.success',
  error: 'settings.autoImport.status.error',
}

const RUN_STATUS_KEYS: Record<BillingRun['status'], MessageKey> = {
  waiting_for_data: 'autoBilling.run.status.waiting_for_data',
  in_review: 'autoBilling.run.status.in_review',
  completed: 'autoBilling.run.status.completed',
}

/*
 * Status von automatischem Hager-Abruf und automatischer Abrechnung für
 * das Dashboard der Administratoren. Liefert Karten für das Raster des
 * Dashboards; Fehler beim Laden blenden die jeweilige Karte aus.
 */
function AdminAutomationStatus() {
  const { t } = useTranslation()
  const [hager, setHager] = useState<HagerSettings | null>(null)
  const [billing, setBilling] = useState<AutoBillingSettings | null>(null)

  useEffect(() => {
    const accessToken = getAccessToken()

    if (accessToken === null) {
      return
    }

    const controller = new AbortController()

    getHagerSettings(accessToken, controller.signal)
      .then(setHager)
      .catch(() => {
        // Status ist optional; Fehler werden hier nicht angezeigt
      })

    getAutoBillingSettings(accessToken, controller.signal)
      .then(setBilling)
      .catch(() => {
        // Status ist optional; Fehler werden hier nicht angezeigt
      })

    return () => {
      controller.abort()
    }
  }, [])

  function runNotes(run: BillingRun): string {
    const notes: string[] = []

    if (run.on_hold > 0) {
      notes.push(t('autoBilling.runs.onHold', { count: run.on_hold }))
    }

    if (run.skipped.length > 0) {
      notes.push(t('autoBilling.runs.skipped', { count: run.skipped.length }))
    }

    return notes.length > 0 ? notes.join(', ') : '–'
  }

  function skippedTitle(run: BillingRun): string | undefined {
    if (run.skipped.length === 0) {
      return undefined
    }

    return run.skipped
      .map((entry) =>
        entry.reason === 'existing_draft' && entry.invoice_id !== null
          ? `${entry.name}: ${t('autoBilling.runs.existingDraft', {
              id: entry.invoice_id,
            })}`
          : `${entry.name}: ${entry.message ?? ''}`,
      )
      .join('\n')
  }

  return (
    <>
      {hager && (
        <article className="card dashboard-automation-card">
          <p className="eyebrow">{t('settings.autoImport.title')}</p>

          {!hager.auto_import_enabled && (
            <p className="muted">{t('dashboard.automation.disabled')}</p>
          )}

          <dl className="settings-status-list">
            {hager.auto_import_enabled && hager.auto_import_next_run_at && (
              <div>
                <dt>{t('settings.autoImport.nextRun')}</dt>
                <dd>{formatUtcDateTime(hager.auto_import_next_run_at)}</dd>
              </div>
            )}

            {hager.last_successful_fetch_at && (
              <div>
                <dt>{t('settings.autoImport.lastSuccess')}</dt>
                <dd>
                  {formatUtcDateTime(hager.last_successful_fetch_at)}{' '}
                  {t('settings.autoImport.lastSuccessHint')}
                </dd>
              </div>
            )}

            <div>
              <dt>{t('settings.autoImport.lastRun')}</dt>
              <dd>
                {hager.auto_import_last_started_at
                  ? `${formatUtcDateTime(
                      hager.auto_import_last_started_at,
                    )} – ${
                      hager.auto_import_last_status
                        ? t(IMPORT_STATUS_KEYS[hager.auto_import_last_status])
                        : t('settings.autoImport.unknown')
                    }`
                  : t('settings.autoImport.notYet')}
              </dd>
            </div>

            {hager.auto_import_last_message && (
              <div>
                <dt>{t('settings.autoImport.result')}</dt>
                <dd
                  className={
                    hager.auto_import_last_status === 'error'
                      ? 'form-error'
                      : undefined
                  }
                >
                  {hager.auto_import_last_message}
                </dd>
              </div>
            )}
          </dl>

          <Link className="table-link" to="/admin/settings">
            {t('dashboard.automation.settingsLink')}
          </Link>
        </article>
      )}

      {billing && (
        <article className="card dashboard-automation-card">
          <p className="eyebrow">{t('autoBilling.title')}</p>

          {!billing.enabled && (
            <p className="muted">{t('dashboard.automation.disabled')}</p>
          )}

          {billing.enabled && !billing.notification_email && (
            <p className="form-error">{t('autoBilling.notificationMissing')}</p>
          )}

          <dl className="settings-status-list">
            {billing.enabled && billing.next_period_start && (
              <div>
                <dt>{t('autoBilling.status.nextPeriod')}</dt>
                <dd>
                  {formatServicePeriod(
                    billing.next_period_start,
                    billing.next_period_end,
                  )}
                </dd>
              </div>
            )}

            {billing.enabled && billing.next_run_at && (
              <div>
                <dt>{t('autoBilling.status.nextRun')}</dt>
                <dd>{formatUtcDateTime(billing.next_run_at)}</dd>
              </div>
            )}

            <div>
              <dt>{t('autoBilling.status.open')}</dt>
              <dd>
                {t('autoBilling.status.openValue', {
                  inReview: billing.open_in_review,
                  onHold: billing.open_on_hold,
                  failed: billing.open_failed,
                })}
              </dd>
            </div>

            {billing.delivery_failed > 0 && (
              <div>
                <dt>{t('autoBilling.status.deliveryFailed')}</dt>
                <dd className="form-error">
                  {t('autoBilling.status.deliveryFailedValue', {
                    count: billing.delivery_failed,
                  })}
                </dd>
              </div>
            )}
          </dl>

          <Link className="table-link" to="/admin/settings#auto-billing">
            {t('dashboard.automation.settingsLink')}
          </Link>
        </article>
      )}

      {billing && billing.runs.length > 0 && (
        <article className="card table-card dashboard-runs-card">
          <div className="section-heading">
            <div>
              <p className="eyebrow">{t('autoBilling.title')}</p>
              <h2>{t('autoBilling.runs.title')}</h2>
            </div>
          </div>

          <div className="table-scroll">
            <table className="data-table compact-table">
              <thead>
                <tr>
                  <th>{t('autoBilling.runs.col.period')}</th>
                  <th>{t('autoBilling.runs.col.status')}</th>
                  <th className="table-number">
                    {t('autoBilling.runs.col.drafts')}
                  </th>
                  <th className="table-number">
                    {t('autoBilling.runs.col.open')}
                  </th>
                  <th>{t('autoBilling.runs.col.reviewUntil')}</th>
                  <th>{t('autoBilling.runs.col.notes')}</th>
                </tr>
              </thead>
              <tbody>
                {billing.runs.map((run) => (
                  <tr key={run.id}>
                    <td>
                      {formatServicePeriod(run.period_start, run.period_end)}
                    </td>
                    <td>{t(RUN_STATUS_KEYS[run.status])}</td>
                    <td className="table-number">{run.drafts_created}</td>
                    <td className="table-number">{run.open_drafts}</td>
                    <td>{formatDate(run.review_due_date)}</td>
                    <td title={skippedTitle(run)}>{runNotes(run)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </article>
      )}
    </>
  )
}

export default AdminAutomationStatus
