import {
  type FormEvent,
  useCallback,
  useEffect,
  useState,
} from 'react'
import { useNavigate } from 'react-router-dom'

import {
  createEnergyPrice,
  type EnergyPrice,
  getEnergyPriceEditableFrom,
  listEnergyPrices,
  SettingsApiError,
  updateEnergyPrice,
} from '../api/settings'
import { getAccessToken } from '../auth/tokenStorage'
import { useAuth } from '../auth/useAuth'
import { useTranslation } from '../i18n/useTranslation'
import { formatDate } from '../utils/dateFormat'
import { formatNumber } from '../utils/numberFormat'

// Kalendertag JJJJ-MM-TT aus einem Zeitpunkt der API (lokale Zeit)
function toDay(value: string): string {
  return value.slice(0, 10)
}

function today(): string {
  const now = new Date()
  const month = String(now.getMonth() + 1).padStart(2, '0')
  const day = String(now.getDate()).padStart(2, '0')

  return `${now.getFullYear()}-${month}-${day}`
}

function normalizeDecimal(value: string): string {
  return value.trim().replace(',', '.')
}

function isDecimal(value: string): boolean {
  return /^\d+(\.\d+)?$/.test(normalizeDecimal(value))
}

/*
 * Energiepreise mit Gültigkeitsdatum: Tarifliste, neuer Tarif und Bearbeiten.
 * Tarife lassen sich nur ab dem Ende des spätesten abgerechneten Zeitraums
 * anlegen oder ändern; das Backend prüft das ebenfalls und berechnet die
 * nicht abgerechneten Ladevorgänge ab dem betroffenen Tag neu.
 */
function AdminEnergyPricesForm() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const { signOut } = useAuth()

  const [prices, setPrices] = useState<EnergyPrice[]>([])
  const [editableFrom, setEditableFrom] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [reloadKey, setReloadKey] = useState(0)

  // null = neuer Tarif, sonst der bearbeitete Tarif
  const [editingId, setEditingId] = useState<number | null>(null)
  const [validFrom, setValidFrom] = useState(today())
  const [gridPriceNet, setGridPriceNet] = useState('')
  const [pvPriceNet, setPvPriceNet] = useState('')
  const [vatRate, setVatRate] = useState('19.00')

  const [isSaving, setIsSaving] = useState(false)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)
  const [successMessage, setSuccessMessage] = useState<string | null>(null)

  const handleUnauthorized = useCallback((): void => {
    signOut()
    navigate('/login', { replace: true })
  }, [navigate, signOut])

  useEffect(() => {
    const controller = new AbortController()

    async function load(): Promise<void> {
      const accessToken = getAccessToken()

      if (accessToken === null) {
        handleUnauthorized()
        return
      }

      setIsLoading(true)

      try {
        const [loadedPrices, loadedEditableFrom] = await Promise.all([
          listEnergyPrices(accessToken, controller.signal),
          getEnergyPriceEditableFrom(accessToken, controller.signal),
        ])

        setPrices(loadedPrices)
        setEditableFrom(loadedEditableFrom)
      } catch (error) {
        if (error instanceof DOMException && error.name === 'AbortError') {
          return
        }

        if (error instanceof SettingsApiError && error.status === 401) {
          handleUnauthorized()
          return
        }

        setErrorMessage(
          error instanceof Error
            ? error.message
            : t('settings.energy.loadFailed'),
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
  }, [handleUnauthorized, reloadKey, t])

  const lockedUntil = editableFrom === null ? null : toDay(editableFrom)

  function isEditable(price: EnergyPrice): boolean {
    return lockedUntil === null || toDay(price.valid_from) >= lockedUntil
  }

  // Tarif, der heute gilt: der jüngste mit Beginn bis heute
  const currentPriceId =
    prices
      .filter((price) => toDay(price.valid_from) <= today())
      .sort((a, b) => b.valid_from.localeCompare(a.valid_from))[0]?.id ?? null

  function startNew(): void {
    setEditingId(null)
    setValidFrom(
      lockedUntil !== null && lockedUntil > today() ? lockedUntil : today(),
    )
    setErrorMessage(null)
    setSuccessMessage(null)
  }

  function startEdit(price: EnergyPrice): void {
    setEditingId(price.id)
    setValidFrom(toDay(price.valid_from))
    setGridPriceNet(price.grid_price_net)
    setPvPriceNet(price.pv_price_net)
    setVatRate(price.vat_rate)
    setErrorMessage(null)
    setSuccessMessage(null)
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault()
    setErrorMessage(null)
    setSuccessMessage(null)

    if (!validFrom) {
      setErrorMessage(t('settings.energy.dateMissing'))
      return
    }

    if (lockedUntil !== null && validFrom < lockedUntil) {
      setErrorMessage(
        t('settings.energy.dateLocked', { date: formatDate(lockedUntil) }),
      )
      return
    }

    if (!isDecimal(gridPriceNet)) {
      setErrorMessage(t('settings.energy.gridInvalid'))
      return
    }

    if (!isDecimal(pvPriceNet)) {
      setErrorMessage(t('settings.energy.pvInvalid'))
      return
    }

    const vat = Number(normalizeDecimal(vatRate))

    if (!isDecimal(vatRate) || vat > 100) {
      setErrorMessage(t('settings.vatRange'))
      return
    }

    const accessToken = getAccessToken()

    if (accessToken === null) {
      handleUnauthorized()
      return
    }

    const payload = {
      valid_from: validFrom,
      grid_price_net: normalizeDecimal(gridPriceNet),
      pv_price_net: normalizeDecimal(pvPriceNet),
      vat_rate: normalizeDecimal(vatRate),
    }

    setIsSaving(true)

    try {
      const saved =
        editingId === null
          ? await createEnergyPrice(accessToken, payload)
          : await updateEnergyPrice(accessToken, editingId, payload)

      setSuccessMessage(
        t('settings.energy.saved', {
          date: formatDate(toDay(saved.valid_from)),
        }),
      )
      setEditingId(null)
      setReloadKey((key) => key + 1)
    } catch (error) {
      if (error instanceof SettingsApiError && error.status === 401) {
        handleUnauthorized()
        return
      }

      setErrorMessage(
        error instanceof Error
          ? error.message
          : t('settings.energy.saveFailed'),
      )
    } finally {
      setIsSaving(false)
    }
  }

  return (
    <form className="card settings-form" onSubmit={handleSubmit}>
      <section className="settings-section">
        <div>
          <h2>{t('settings.energy.title')}</h2>
          <p className="muted">{t('settings.energy.intro')}</p>
        </div>

        {lockedUntil !== null && (
          <p className="muted">
            {t('settings.energy.lockedHint', {
              date: formatDate(lockedUntil),
            })}
          </p>
        )}

        {isLoading ? (
          <p className="muted">{t('common.loading')}</p>
        ) : prices.length === 0 ? (
          <p className="muted">{t('settings.energy.none')}</p>
        ) : (
          <div className="table-scroll">
            <table className="data-table compact-table">
              <thead>
                <tr>
                  <th>{t('settings.energy.validFrom')}</th>
                  <th className="table-number">{t('settings.energy.gridPrice')}</th>
                  <th className="table-number">{t('settings.energy.pvPrice')}</th>
                  <th className="table-number">{t('settings.energy.vat')}</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {prices.map((price) => (
                  <tr key={price.id}>
                    <td>
                      {formatDate(toDay(price.valid_from))}
                      {price.id === currentPriceId && (
                        <>
                          {' '}
                          <span className="status-badge">
                            {t('settings.energy.current')}
                          </span>
                        </>
                      )}
                    </td>
                    <td className="table-number">
                      {formatNumber(price.grid_price_net, 4)}
                    </td>
                    <td className="table-number">
                      {formatNumber(price.pv_price_net, 4)}
                    </td>
                    <td className="table-number">
                      {formatNumber(price.vat_rate, 2)}
                    </td>
                    <td>
                      {isEditable(price) ? (
                        <button
                          className="button button-secondary"
                          type="button"
                          disabled={isSaving}
                          onClick={() => {
                            startEdit(price)
                          }}
                        >
                          {t('common.edit')}
                        </button>
                      ) : (
                        <span className="muted">
                          {t('settings.energy.billed')}
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="settings-section">
        <div>
          <h2>
            {editingId === null
              ? t('settings.energy.new')
              : t('settings.energy.editTitle')}
          </h2>
          <p className="muted">{t('settings.energy.repriceHint')}</p>
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

        <div className="form-grid">
          <label className="form-field">
            <span>{t('settings.energy.validFrom')}</span>
            <input
              type="date"
              value={validFrom}
              min={lockedUntil ?? undefined}
              required
              onChange={(event) => {
                setValidFrom(event.target.value)
              }}
            />
          </label>

          <label className="form-field">
            <span>{t('settings.energy.gridPrice')}</span>
            <input
              type="text"
              inputMode="decimal"
              value={gridPriceNet}
              required
              onChange={(event) => {
                setGridPriceNet(event.target.value)
              }}
            />
          </label>

          <label className="form-field">
            <span>{t('settings.energy.pvPrice')}</span>
            <input
              type="text"
              inputMode="decimal"
              value={pvPriceNet}
              required
              onChange={(event) => {
                setPvPriceNet(event.target.value)
              }}
            />
          </label>

          <label className="form-field">
            <span>{t('settings.energy.vat')}</span>
            <input
              type="text"
              inputMode="decimal"
              value={vatRate}
              required
              onChange={(event) => {
                setVatRate(event.target.value)
              }}
            />
          </label>
        </div>
      </section>

      <div className="form-actions">
        <button
          className="button button-primary"
          type="submit"
          disabled={isSaving}
        >
          {isSaving ? t('settings.energy.saving') : t('settings.energy.save')}
        </button>

        {editingId !== null ? (
          <button
            className="button button-secondary"
            type="button"
            disabled={isSaving}
            onClick={startNew}
          >
            {t('common.cancel')}
          </button>
        ) : null}
      </div>
    </form>
  )
}

export default AdminEnergyPricesForm
