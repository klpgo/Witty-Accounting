import {
  type FormEvent,
  useCallback,
  useEffect,
  useState,
} from 'react'
import { useNavigate } from 'react-router-dom'

import {
  getCurrentEnergyPrice,
  getGlobalSettings,
  SettingsApiError,
  updateCurrentEnergyPrice,
  updateGlobalSettings,
  type EnergyPrice,
} from '../api/settings'
import { getAccessToken } from '../auth/tokenStorage'
import { useAuth } from '../auth/useAuth'
import { useAppSettings } from '../settings/useAppSettings'

function normalizeDecimal(value: string): string {
  return value.trim().replace(',', '.')
}

function decimalValuesEqual(
  first: string,
  second: string,
): boolean {
  return (
    Number(normalizeDecimal(first)) ===
    Number(normalizeDecimal(second))
  )
}

function formatValidFrom(
  value: string,
): string {
  const [year, month, day] =
    value.slice(0, 10).split('-')

  return `${day}.${month}.${year}`
}

function AdminSettingsPage() {
  const navigate = useNavigate()
  const { signOut } = useAuth()
  const { refreshSettings } = useAppSettings()

  const [appName, setAppName] = useState('')
  const [
    monthlyBaseFeeNet,
    setMonthlyBaseFeeNet,
  ] = useState('')
  const [
    monthlyBaseFeeVatRate,
    setMonthlyBaseFeeVatRate,
  ] = useState('')
  const [
    invoicePaymentTermDays,
    setInvoicePaymentTermDays,
  ] = useState('')
  const [
    currentEnergyPrice,
    setCurrentEnergyPrice,
  ] = useState<EnergyPrice | null>(null)

  const [
    gridPriceNet,
    setGridPriceNet,
  ] = useState('')

  const [
    pvPriceNet,
    setPvPriceNet,
  ] = useState('')

  const [
    energyVatRate,
    setEnergyVatRate,
  ] = useState('')

  const [
    isSavingEnergyPrice,
    setIsSavingEnergyPrice,
  ] = useState(false)

  const [
    energyErrorMessage,
    setEnergyErrorMessage,
  ] = useState<string | null>(null)

  const [
    energySuccessMessage,
    setEnergySuccessMessage,
  ] = useState<string | null>(null)

  const [isLoading, setIsLoading] =
    useState(true)
  const [isSaving, setIsSaving] =
    useState(false)

  const [
    errorMessage,
    setErrorMessage,
  ] = useState<string | null>(null)

  const [
    successMessage,
    setSuccessMessage,
  ] = useState<string | null>(null)

  const handleRequestError = useCallback(
    (
      error: unknown,
      fallbackMessage: string,
    ): void => {
      if (
        error instanceof SettingsApiError &&
        error.status === 401
      ) {
        signOut()

        navigate('/login', {
          replace: true,
        })

        return
      }

      setErrorMessage(
        error instanceof Error
          ? error.message
          : fallbackMessage,
      )
    },
    [navigate, signOut],
  )

  useEffect(() => {
    const controller = new AbortController()

    async function loadSettings(): Promise<void> {
      const accessToken = getAccessToken()

      if (accessToken === null) {
        signOut()

        navigate('/login', {
          replace: true,
        })

        return
      }

      setIsLoading(true)
      setErrorMessage(null)

      try {
        const loadedSettings =
          await getGlobalSettings(
            accessToken,
            controller.signal,
          )

        let loadedEnergyPrice:
          EnergyPrice | null = null

        try {
          loadedEnergyPrice =
            await getCurrentEnergyPrice(
              accessToken,
              controller.signal,
            )
        } catch (error) {
          if (
            !(
              error instanceof SettingsApiError &&
              error.status === 404
            )
          ) {
            throw error
          }
        }

        setAppName(loadedSettings.app_name)
        setMonthlyBaseFeeNet(
          loadedSettings.monthly_base_fee_net,
        )
        setMonthlyBaseFeeVatRate(
          loadedSettings.monthly_base_fee_vat_rate,
        )
        setInvoicePaymentTermDays(
          String(
            loadedSettings
              .invoice_payment_term_days,
          ),
        )
        if (loadedEnergyPrice !== null) {
          setCurrentEnergyPrice(
            loadedEnergyPrice,
          )
          setGridPriceNet(
            loadedEnergyPrice.grid_price_net,
          )
          setPvPriceNet(
            loadedEnergyPrice.pv_price_net,
          )
          setEnergyVatRate(
            loadedEnergyPrice.vat_rate,
          )
        }
      } catch (error) {
        if (
          error instanceof DOMException &&
          error.name === 'AbortError'
        ) {
          return
        }

        handleRequestError(
          error,
          'Die Einstellungen konnten nicht geladen werden.',
        )
      } finally {
        if (!controller.signal.aborted) {
          setIsLoading(false)
        }
      }
    }

    void loadSettings()

    return () => {
      controller.abort()
    }
  }, [
    handleRequestError,
    navigate,
    signOut,
  ])

  async function handleSubmit(
    event: FormEvent<HTMLFormElement>,
  ): Promise<void> {
    event.preventDefault()

    const normalizedAppName = appName.trim()
    const normalizedBaseFee =
      normalizeDecimal(monthlyBaseFeeNet)
    const normalizedVatRate =
      normalizeDecimal(monthlyBaseFeeVatRate)
    const paymentTermDays = Number(
      invoicePaymentTermDays,
    )

    if (!normalizedAppName) {
      setErrorMessage(
        'Der Anwendungsname darf nicht leer sein.',
      )
      setSuccessMessage(null)
      return
    }

    if (
      !Number.isFinite(
        Number(normalizedBaseFee),
      ) ||
      Number(normalizedBaseFee) < 0
    ) {
      setErrorMessage(
        'Die monatliche Grundgebühr muss mindestens 0 sein.',
      )
      setSuccessMessage(null)
      return
    }

    if (
      !Number.isFinite(
        Number(normalizedVatRate),
      ) ||
      Number(normalizedVatRate) < 0 ||
      Number(normalizedVatRate) > 100
    ) {
      setErrorMessage(
        'Der Umsatzsteuersatz muss zwischen 0 und 100 liegen.',
      )
      setSuccessMessage(null)
      return
    }

    if (
      !Number.isInteger(paymentTermDays) ||
      paymentTermDays < 0 ||
      paymentTermDays > 3650
    ) {
      setErrorMessage(
        'Das Zahlungsziel muss eine ganze Zahl zwischen 0 und 3650 sein.',
      )
      setSuccessMessage(null)
      return
    }

    const accessToken = getAccessToken()

    if (accessToken === null) {
      signOut()

      navigate('/login', {
        replace: true,
      })

      return
    }

    setIsSaving(true)
    setErrorMessage(null)
    setSuccessMessage(null)

    try {
      const updatedSettings =
        await updateGlobalSettings(
          accessToken,
          {
            app_name: normalizedAppName,
            monthly_base_fee_net:
              normalizedBaseFee,
            monthly_base_fee_vat_rate:
              normalizedVatRate,
            invoice_payment_term_days:
              paymentTermDays,
          },
        )

      setAppName(updatedSettings.app_name)
      setMonthlyBaseFeeNet(
        updatedSettings.monthly_base_fee_net,
      )
      setMonthlyBaseFeeVatRate(
        updatedSettings
          .monthly_base_fee_vat_rate,
      )
      setInvoicePaymentTermDays(
        String(
          updatedSettings
            .invoice_payment_term_days,
        ),
      )

      await refreshSettings()

      setSuccessMessage(
        'Die globalen Einstellungen wurden gespeichert.',
      )
    } catch (error) {
      handleRequestError(
        error,
        'Die Einstellungen konnten nicht gespeichert werden.',
      )
    } finally {
      setIsSaving(false)
    }
  }

  async function handleEnergyPriceSubmit(
    event: FormEvent<HTMLFormElement>,
  ): Promise<void> {
    event.preventDefault()

    const normalizedGridPrice =
      normalizeDecimal(gridPriceNet)

    const normalizedPvPrice =
      normalizeDecimal(pvPriceNet)

    const normalizedVatRate =
      normalizeDecimal(energyVatRate)

    const gridPriceValue = Number(
      normalizedGridPrice,
    )
    const pvPriceValue = Number(
      normalizedPvPrice,
    )
    const vatRateValue = Number(
      normalizedVatRate,
    )

    setEnergyErrorMessage(null)
    setEnergySuccessMessage(null)

    if (
      !Number.isFinite(gridPriceValue) ||
      gridPriceValue < 0
    ) {
      setEnergyErrorMessage(
        'Der Netzpreis muss mindestens 0 sein.',
      )
      return
    }

    if (
      !Number.isFinite(pvPriceValue) ||
      pvPriceValue < 0
    ) {
      setEnergyErrorMessage(
        'Der PV-Preis muss mindestens 0 sein.',
      )
      return
    }

    if (
      !Number.isFinite(vatRateValue) ||
      vatRateValue < 0 ||
      vatRateValue > 100
    ) {
      setEnergyErrorMessage(
        'Der Umsatzsteuersatz muss zwischen 0 und 100 liegen.',
      )
      return
    }

    if (
      currentEnergyPrice !== null &&
      decimalValuesEqual(
        normalizedGridPrice,
        currentEnergyPrice.grid_price_net,
      ) &&
      decimalValuesEqual(
        normalizedPvPrice,
        currentEnergyPrice.pv_price_net,
      ) &&
      decimalValuesEqual(
        normalizedVatRate,
        currentEnergyPrice.vat_rate,
      )
    ) {
      setEnergySuccessMessage(
        'Es wurden keine Preisänderungen vorgenommen.',
      )
      return
    }

    const accessToken = getAccessToken()

    if (accessToken === null) {
      signOut()

      navigate('/login', {
        replace: true,
      })

      return
    }

    setIsSavingEnergyPrice(true)

    try {
      const updatedEnergyPrice =
        await updateCurrentEnergyPrice(
          accessToken,
          {
            grid_price_net:
              normalizedGridPrice,
            pv_price_net:
              normalizedPvPrice,
            vat_rate:
              normalizedVatRate,
          },
        )

      setCurrentEnergyPrice(
        updatedEnergyPrice,
      )
      setGridPriceNet(
        updatedEnergyPrice.grid_price_net,
      )
      setPvPriceNet(
        updatedEnergyPrice.pv_price_net,
      )
      setEnergyVatRate(
        updatedEnergyPrice.vat_rate,
      )

      setEnergySuccessMessage(
        'Die Energiepreise wurden mit ' +
          `Gültigkeit ab ${formatValidFrom(
            updatedEnergyPrice.valid_from,
          )} gespeichert.`,
      )
    } catch (error) {
      if (
        error instanceof SettingsApiError &&
        error.status === 401
      ) {
        signOut()

        navigate('/login', {
          replace: true,
        })

        return
      }

      setEnergyErrorMessage(
        error instanceof Error
          ? error.message
          : 'Die Energiepreise konnten nicht gespeichert werden.',
      )
    } finally {
      setIsSavingEnergyPrice(false)
    }
  }

  return (
    <div className="page admin-page">
      <header className="page-header">
        <div>
          <p className="eyebrow">
            Administration
          </p>

          <h1>Einstellungen</h1>

          <p className="muted">
            Anwendungsname und Vorgaben für neue
            Rechnungen verwalten.
          </p>
        </div>
      </header>

      {isLoading && (
        <section className="card">
          <p className="muted">
            Einstellungen werden geladen …
          </p>
        </section>
      )}

      {!isLoading && errorMessage && (
        <section
          className="card form-error"
          role="alert"
        >
          {errorMessage}
        </section>
      )}

      {!isLoading && successMessage && (
        <section
          className="card form-success"
          role="status"
        >
          {successMessage}
        </section>
      )}

      {!isLoading && (
        <form
          className="card settings-form"
          onSubmit={handleSubmit}
        >
          <section className="settings-section">
            <h2>Allgemein</h2>

            <label className="form-field settings-name-field">
              <span>Anwendungsname</span>

              <input
                type="text"
                value={appName}
                maxLength={255}
                onChange={(event) => {
                  setAppName(event.target.value)
                }}
                required
              />

              <small className="muted">
                Wird im Login, in der Kopfzeile und
                als Browser-Titel angezeigt.
              </small>
            </label>
          </section>

          <h2>Abrechnung</h2>

          <div className="form-grid settings-billing-grid">
            <label className="form-field">
              <span>
                Monatliche Grundgebühr netto
              </span>

              <input
                type="text"
                inputMode="decimal"
                value={monthlyBaseFeeNet}
                onChange={(event) => {
                  setMonthlyBaseFeeNet(
                    event.target.value,
                  )
                }}
                required
              />

              <small className="muted">
                Betrag je zugeordneter
                RFID-Karte und Monat.
              </small>
            </label>

            <label className="form-field">
              <span>
                Umsatzsteuer Grundgebühr (%)
              </span>

              <input
                type="text"
                inputMode="decimal"
                value={monthlyBaseFeeVatRate}
                onChange={(event) => {
                  setMonthlyBaseFeeVatRate(
                    event.target.value,
                  )
                }}
                required
              />
            </label>

            <label className="form-field">
              <span>
                Zahlungsziel in Tagen
              </span>

              <input
                type="number"
                min="0"
                max="3650"
                step="1"
                value={invoicePaymentTermDays}
                onChange={(event) => {
                  setInvoicePaymentTermDays(
                    event.target.value,
                  )
                }}
                required
              />

              <small className="muted">
                Wird bei neu finalisierten
                Rechnungen zum Rechnungsdatum
                addiert.
              </small>
            </label>
          </div>

          <div className="settings-actions">
            <button
              className="button button-primary"
              type="submit"
              disabled={isSaving}
            >
              {isSaving
                ? 'Einstellungen werden gespeichert …'
                : 'Einstellungen speichern'}
            </button>
          </div>
        </form>
      )}
      {!isLoading && (
        <form
          className="card settings-form"
          onSubmit={handleEnergyPriceSubmit}
        >
          <section className="settings-section">
            <div>
              <h2>Energiepreise</h2>

              <p className="muted">
                Aktuell gültige Nettopreise je
                Kilowattstunde verwalten.
              </p>
            </div>

            {currentEnergyPrice !== null ? (
              <p className="muted">
                Aktuell gültig seit{' '}
                <strong>
                  {formatValidFrom(
                    currentEnergyPrice.valid_from,
                  )}
                </strong>
              </p>
            ) : (
              <p className="muted">
                Es ist noch kein Energietarif
                vorhanden.
              </p>
            )}

            {energyErrorMessage && (
              <div
                className="form-error"
                role="alert"
              >
                {energyErrorMessage}
              </div>
            )}

            {energySuccessMessage && (
              <div
                className="form-success"
                role="status"
              >
                {energySuccessMessage}
              </div>
            )}

            <div className="form-grid settings-billing-grid">
              <label className="form-field">
                <span>
                  Netzpreis netto je kWh
                </span>

                <input
                  type="text"
                  inputMode="decimal"
                  value={gridPriceNet}
                  onChange={(event) => {
                    setGridPriceNet(
                      event.target.value,
                    )
                  }}
                  required
                />
              </label>

              <label className="form-field">
                <span>
                  PV-Preis netto je kWh
                </span>

                <input
                  type="text"
                  inputMode="decimal"
                  value={pvPriceNet}
                  onChange={(event) => {
                    setPvPriceNet(
                      event.target.value,
                    )
                  }}
                  required
                />
              </label>

              <label className="form-field">
                <span>
                  Umsatzsteuer Energie (%)
                </span>

                <input
                  type="text"
                  inputMode="decimal"
                  value={energyVatRate}
                  onChange={(event) => {
                    setEnergyVatRate(
                      event.target.value,
                    )
                  }}
                  required
                />
              </label>
            </div>
          </section>

          <div className="settings-actions">
            <button
              className="button button-primary"
              type="submit"
              disabled={isSavingEnergyPrice}
            >
              {isSavingEnergyPrice
                ? 'Energiepreise werden gespeichert …'
                : 'Energiepreise speichern'}
            </button>
          </div>
        </form>
      )}
    </div>
  )
}

export default AdminSettingsPage
