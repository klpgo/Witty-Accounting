import {
  type FormEvent,
  useCallback,
  useEffect,
  useState,
} from 'react'
import { useNavigate } from 'react-router-dom'

import {
  getAutoBillingPreview,
  getAutoBillingSettings,
  SettingsApiError,
  updateAutoBillingSettings,
  type AutoBillingPreview,
  type AutoBillingSettings,
  type BillingInterval,
} from '../api/settings'
import { getAccessToken } from '../auth/tokenStorage'
import { useAuth } from '../auth/useAuth'
import type { MessageKey } from '../i18n/de'
import { useTranslation } from '../i18n/useTranslation'
import {
  formatServicePeriod,
  formatUtcDateTime,
} from '../utils/dateFormat'

const INTERVAL_KEYS: Record<BillingInterval, MessageKey> = {
  weekly: 'autoBilling.interval.weekly',
  monthly: 'autoBilling.interval.monthly',
  quarterly: 'autoBilling.interval.quarterly',
}

const WEEKDAY_KEYS: MessageKey[] = [
  'autoBilling.weekday.1',
  'autoBilling.weekday.2',
  'autoBilling.weekday.3',
  'autoBilling.weekday.4',
  'autoBilling.weekday.5',
  'autoBilling.weekday.6',
  'autoBilling.weekday.7',
]

const DELIVERY_KEYS: Record<string, MessageKey> = {
  email: 'autoBilling.delivery.email',
  portal: 'autoBilling.delivery.portal',
  post: 'autoBilling.delivery.post',
}

/*
 * Automatische Abrechnung: Zeitplan, Fristen, Hinweisadresse, Probelauf
 * und die letzten Abrechnungsläufe.
 */
function AdminAutoBillingForm() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const { signOut } = useAuth()

  const [settings, setSettings] = useState<AutoBillingSettings | null>(null)
  const [enabled, setEnabled] = useState(false)
  const [billingInterval, setBillingInterval] =
    useState<BillingInterval>('monthly')
  const [cutoffDay, setCutoffDay] = useState(0)
  const [graceDays, setGraceDays] = useState('2')
  const [reviewDays, setReviewDays] = useState('7')
  const [runTime, setRunTime] = useState('06:00')

  const [preview, setPreview] = useState<AutoBillingPreview | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [isSaving, setIsSaving] = useState(false)
  const [isPreviewing, setIsPreviewing] = useState(false)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)
  const [successMessage, setSuccessMessage] = useState<string | null>(null)

  const handleUnauthorized = useCallback((): void => {
    signOut()
    navigate('/login', { replace: true })
  }, [navigate, signOut])

  const applySettings = useCallback((loaded: AutoBillingSettings): void => {
    setSettings(loaded)
    setEnabled(loaded.enabled)
    setBillingInterval(loaded.interval)
    setCutoffDay(loaded.cutoff_day)
    setGraceDays(String(loaded.grace_days))
    setReviewDays(String(loaded.review_days))
    setRunTime(loaded.run_time)
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
        applySettings(
          await getAutoBillingSettings(accessToken, controller.signal),
        )
      } catch (error) {
        if (error instanceof DOMException && error.name === 'AbortError') {
          return
        }

        if (error instanceof SettingsApiError && error.status === 401) {
          handleUnauthorized()
          return
        }

        setErrorMessage(
          error instanceof Error ? error.message : t('autoBilling.loadFailed'),
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
  }, [applySettings, handleUnauthorized, t])

  function handleIntervalChange(value: BillingInterval): void {
    setBillingInterval(value)

    // Stichtag passend zum Intervall vorbelegen
    if (value === 'weekly' && (cutoffDay < 1 || cutoffDay > 7)) {
      setCutoffDay(7)
    } else if (value !== 'weekly' && billingInterval === 'weekly') {
      setCutoffDay(0)
    }
  }

  async function handleSubmit(
    event: FormEvent<HTMLFormElement>,
  ): Promise<void> {
    event.preventDefault()

    const accessToken = getAccessToken()

    if (accessToken === null) {
      handleUnauthorized()
      return
    }

    setIsSaving(true)
    setErrorMessage(null)
    setSuccessMessage(null)

    try {
      applySettings(
        await updateAutoBillingSettings(accessToken, {
          enabled,
          interval: billingInterval,
          cutoff_day: cutoffDay,
          grace_days: Number(graceDays),
          review_days: Number(reviewDays),
          run_time: runTime,
        }),
      )
      setPreview(null)
      setSuccessMessage(t('autoBilling.saved'))
    } catch (error) {
      if (error instanceof SettingsApiError && error.status === 401) {
        handleUnauthorized()
        return
      }

      setErrorMessage(
        error instanceof Error ? error.message : t('autoBilling.saveFailed'),
      )
    } finally {
      setIsSaving(false)
    }
  }

  async function handlePreview(): Promise<void> {
    const accessToken = getAccessToken()

    if (accessToken === null) {
      handleUnauthorized()
      return
    }

    setIsPreviewing(true)
    setErrorMessage(null)

    try {
      setPreview(await getAutoBillingPreview(accessToken))
    } catch (error) {
      if (error instanceof SettingsApiError && error.status === 401) {
        handleUnauthorized()
        return
      }

      setErrorMessage(
        error instanceof Error ? error.message : t('autoBilling.previewFailed'),
      )
    } finally {
      setIsPreviewing(false)
    }
  }

  if (isLoading) {
    return (
      <section className="card">
        <p className="muted">{t('autoBilling.loading')}</p>
      </section>
    )
  }

  return (
    <form
      className="card settings-form"
      id="auto-billing"
      onSubmit={handleSubmit}
    >
      <section className="settings-section">
        <div>
          <h2>{t('autoBilling.title')}</h2>
          <p className="muted">{t('autoBilling.intro')}</p>
        </div>

        {errorMessage && (
          <div className="form-error" role="alert">
            {errorMessage}
          </div>
        )}

        {successMessage && (
          <div className="form-success" role="status">
            {successMessage}
          </div>
        )}

        <label className="settings-checkbox-control">
          <input
            type="checkbox"
            checked={enabled}
            onChange={(event) => {
              setEnabled(event.target.checked)
            }}
          />
          {t('autoBilling.enable')}
        </label>

        <small className="muted">{t('autoBilling.enableHint')}</small>

        <div className="form-grid settings-business-grid">
          <label className="form-field">
            <span>{t('autoBilling.interval')}</span>
            <select
              value={billingInterval}
              onChange={(event) => {
                handleIntervalChange(event.target.value as BillingInterval)
              }}
            >
              {(Object.keys(INTERVAL_KEYS) as BillingInterval[]).map(
                (value) => (
                  <option key={value} value={value}>
                    {t(INTERVAL_KEYS[value])}
                  </option>
                ),
              )}
            </select>
          </label>

          <label className="form-field">
            <span>{t('autoBilling.cutoffDay')}</span>
            <select
              value={cutoffDay}
              onChange={(event) => {
                setCutoffDay(Number(event.target.value))
              }}
            >
              {billingInterval === 'weekly'
                ? WEEKDAY_KEYS.map((key, index) => (
                    <option key={key} value={index + 1}>
                      {t(key)}
                    </option>
                  ))
                : [
                    <option key={0} value={0}>
                      {t('autoBilling.cutoff.lastDay')}
                    </option>,
                    ...Array.from({ length: 28 }, (_, index) => (
                      <option key={index + 1} value={index + 1}>
                        {t('autoBilling.cutoff.dayOfMonth', {
                          day: index + 1,
                        })}
                      </option>
                    )),
                  ]}
            </select>
            {billingInterval === 'quarterly' && (
              <small className="muted">
                {t('autoBilling.cutoff.quarterlyHint')}
              </small>
            )}
          </label>

          <label className="form-field">
            <span>{t('autoBilling.graceDays')}</span>
            <input
              type="number"
              min={0}
              max={31}
              step={1}
              value={graceDays}
              onChange={(event) => {
                setGraceDays(event.target.value)
              }}
            />
            <small className="muted">{t('autoBilling.graceHint')}</small>
          </label>

          <label className="form-field">
            <span>{t('autoBilling.reviewDays')}</span>
            <input
              type="number"
              min={1}
              max={60}
              step={1}
              value={reviewDays}
              onChange={(event) => {
                setReviewDays(event.target.value)
              }}
            />
          </label>

          <label className="form-field">
            <span>{t('autoBilling.runTime')}</span>
            <input
              type="time"
              value={runTime}
              onChange={(event) => {
                setRunTime(event.target.value)
              }}
            />
          </label>

        </div>

        {settings && (
          <p
            className={
              settings.notification_email ? 'muted' : 'form-error'
            }
          >
            {settings.notification_email
              ? t('autoBilling.notificationInfo', {
                  email: settings.notification_email,
                })
              : t('autoBilling.notificationMissing')}
          </p>
        )}

        {settings && (
          <p className="muted">
            {settings.waits_for_hager_fetch
              ? t('autoBilling.hagerHint')
              : t('autoBilling.manualImportHint')}
          </p>
        )}

      </section>

      <div className="settings-actions">
        <button
          className="button button-primary"
          type="submit"
          disabled={isSaving}
        >
          {isSaving ? t('autoBilling.saving') : t('autoBilling.save')}
        </button>

        <button
          className="button button-secondary"
          type="button"
          disabled={isPreviewing || isSaving}
          onClick={() => {
            void handlePreview()
          }}
        >
          {isPreviewing
            ? t('autoBilling.previewLoading')
            : t('autoBilling.preview')}
        </button>
      </div>

      {preview && (
        <section className="settings-section">
          <h3>
            {t('autoBilling.previewTitle', {
              period: formatServicePeriod(
                preview.period_start,
                preview.period_end,
              ),
            })}
          </h3>

          {!preview.data_ready && (
            <p className="form-error">{t('autoBilling.previewDataPending')}</p>
          )}

          {preview.customers.length === 0 ? (
            <p className="muted">{t('autoBilling.previewEmpty')}</p>
          ) : (
            <>
              <p className="muted">
                {t('autoBilling.previewIntro', {
                  date: formatUtcDateTime(preview.run_at),
                })}
              </p>

              <div className="table-scroll">
                <table className="data-table compact-table">
                  <thead>
                    <tr>
                      <th>{t('autoBilling.preview.col.customer')}</th>
                      <th>{t('autoBilling.preview.col.delivery')}</th>
                      <th>{t('autoBilling.preview.col.note')}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {preview.customers.map((customer) => (
                      <tr key={customer.user_id}>
                        <td>
                          <strong>{customer.name}</strong>
                          <br />
                          <span className="muted">{customer.email}</span>
                        </td>
                        <td>
                          {DELIVERY_KEYS[customer.delivery]
                            ? t(DELIVERY_KEYS[customer.delivery])
                            : customer.delivery}
                        </td>
                        <td>
                          {customer.existing_draft_id !== null
                            ? t('autoBilling.note.existingDraft', {
                                id: customer.existing_draft_id,
                              })
                            : !customer.has_address
                              ? t('autoBilling.note.noAddress')
                              : '–'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </section>
      )}

    </form>
  )
}

export default AdminAutoBillingForm
