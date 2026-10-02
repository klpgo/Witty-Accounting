import {
  type FormEvent,
  useCallback,
  useEffect,
  useState,
} from 'react'
import { useNavigate } from 'react-router-dom'

import {
  getGlobalSettings,
  SettingsApiError,
  updateGlobalSettings,
} from '../api/settings'
import { getAccessToken } from '../auth/tokenStorage'
import { useAuth } from '../auth/useAuth'
import { useAppSettings } from '../settings/useAppSettings'
import { useTranslation } from '../i18n/useTranslation'
import AdminSmtpSettingsForm from './AdminSmtpSettingsForm'
import AdminPasswordPolicyForm from './AdminPasswordPolicyForm'
import AdminAccessSettingsForm from './AdminAccessSettingsForm'
import AdminEnergyPricesForm from './AdminEnergyPricesForm'
import AdminInvoiceExportSettingsForm from './AdminInvoiceExportSettingsForm'
import AdminHagerSettingsForm from './AdminHagerSettingsForm'
import AdminWallboxesForm from './AdminWallboxesForm'

function normalizeDecimal(value: string): string {
  return value.trim().replace(',', '.')
}


function AdminSettingsPage() {
  const navigate = useNavigate()
  const { signOut } = useAuth()
  const { refreshSettings } = useAppSettings()
  const { t } = useTranslation()

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
    postalDeliveryFeeNet,
    setPostalDeliveryFeeNet,
  ] = useState('')
  const [
    billingStartDate,
    setBillingStartDate,
  ] = useState('')
  const [locale, setLocale] = useState('de-DE')
  const [defaultLanguageSetting, setDefaultLanguageSetting] =
    useState('de')
  const [currency, setCurrency] = useState('EUR')
  const [
    invoicePaymentTermDays,
    setInvoicePaymentTermDays,
  ] = useState('')
  const [
    invoiceIssuerName,
    setInvoiceIssuerName,
  ] = useState('')

  const [
    invoiceIssuerAddress,
    setInvoiceIssuerAddress,
  ] = useState('')

  const [
    invoiceTaxNumber,
    setInvoiceTaxNumber,
  ] = useState('')

  const [
    invoiceVatId,
    setInvoiceVatId,
  ] = useState('')

  const [
    invoiceBankName,
    setInvoiceBankName,
  ] = useState('')

  const [
    invoiceIban,
    setInvoiceIban,
  ] = useState('')

  const [
    invoiceBic,
    setInvoiceBic,
  ] = useState('')

  const [
    invoiceIssuerPhone,
    setInvoiceIssuerPhone,
  ] = useState('')

  const [
    invoiceNumberPrefix,
    setInvoiceNumberPrefix,
  ] = useState('RE')

  const [
    invoicePdfFormat,
    setInvoicePdfFormat,
  ] = useState<'standard' | 'pdfa-2b'>(
    'standard',
  )

  const [
    invoiceGirocodeEnabled,
    setInvoiceGirocodeEnabled,
  ] = useState(false)


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

        setAppName(loadedSettings.app_name)
        setMonthlyBaseFeeNet(
          loadedSettings.monthly_base_fee_net,
        )
        setMonthlyBaseFeeVatRate(
          loadedSettings.monthly_base_fee_vat_rate,
        )
        setPostalDeliveryFeeNet(
          loadedSettings.postal_delivery_fee_net,
        )
        setBillingStartDate(
          loadedSettings.billing_start_date ?? '',
        )
        setLocale(loadedSettings.locale)
        setDefaultLanguageSetting(loadedSettings.default_language)
        setCurrency(loadedSettings.currency)
        setInvoicePaymentTermDays(
          String(
            loadedSettings
              .invoice_payment_term_days,
          ),
        )
        setInvoiceIssuerName(
          loadedSettings.invoice_issuer_name ?? '',
        )
        setInvoiceIssuerAddress(
          loadedSettings.invoice_issuer_address ?? '',
        )
        setInvoiceTaxNumber(
          loadedSettings.invoice_tax_number ?? '',
        )
        setInvoiceVatId(
          loadedSettings.invoice_vat_id ?? '',
        )
        setInvoiceBankName(
          loadedSettings.invoice_bank_name ?? '',
        )
        setInvoiceIban(
          loadedSettings.invoice_iban ?? '',
        )
        setInvoiceBic(
          loadedSettings.invoice_bic ?? '',
        )
        setInvoiceIssuerPhone(
          loadedSettings.invoice_issuer_phone ??
            '',
        )
        setInvoiceNumberPrefix(
          loadedSettings.invoice_number_prefix,
        )
        setInvoicePdfFormat(
          loadedSettings.invoice_pdf_format,
        )
        setInvoiceGirocodeEnabled(
          loadedSettings.invoice_girocode_enabled,
        )
      } catch (error) {
        if (
          error instanceof DOMException &&
          error.name === 'AbortError'
        ) {
          return
        }

        handleRequestError(
          error,
          t('settings.loadFailed'),
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
    const normalizedPostalDeliveryFee =
      normalizeDecimal(postalDeliveryFeeNet)
    const paymentTermDays = Number(
      invoicePaymentTermDays,
    )
    const normalizedIssuerName =
      invoiceIssuerName.trim()
    const normalizedIssuerAddress =
      invoiceIssuerAddress.trim()
    const normalizedTaxNumber =
      invoiceTaxNumber.trim()
    const normalizedVatId =
      invoiceVatId.trim()
    const normalizedBankName =
      invoiceBankName.trim()
    const normalizedIban = invoiceIban
      .replace(/\s+/g, '')
      .toUpperCase()
    const normalizedBic = invoiceBic
      .trim()
      .toUpperCase()
    const normalizedIssuerPhone =
      invoiceIssuerPhone.trim()
    const normalizedNumberPrefix =
      invoiceNumberPrefix
        .trim()
        .toUpperCase()

    const hasInvoiceBusinessSettings = [
      normalizedIssuerName,
      normalizedIssuerAddress,
      normalizedTaxNumber,
      normalizedVatId,
      normalizedBankName,
      normalizedIban,
      normalizedBic,
    ].some((value) => value.length > 0)

    if (!normalizedAppName) {
      setErrorMessage(
        t('settings.appNameMissing'),
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
        t('settings.baseFeeInvalid'),
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
        t('settings.vatRange'),
      )
      setSuccessMessage(null)
      return
    }

    if (
      !Number.isFinite(
        Number(normalizedPostalDeliveryFee),
      ) ||
      Number(normalizedPostalDeliveryFee) < 0
    ) {
      setErrorMessage(
        t('settings.postalFeeInvalid'),
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
        t('settings.paymentTermInvalid'),
      )
      setSuccessMessage(null)
      return
    }

    if (
      hasInvoiceBusinessSettings &&
      !normalizedIssuerName
    ) {
      setErrorMessage(
        t('settings.issuer.nameMissing'),
      )
      setSuccessMessage(null)
      return
    }

    if (
      hasInvoiceBusinessSettings &&
      !normalizedIssuerAddress
    ) {
      setErrorMessage(
        t('settings.issuer.addressMissing'),
      )
      setSuccessMessage(null)
      return
    }

    if (
      hasInvoiceBusinessSettings &&
      !normalizedTaxNumber &&
      !normalizedVatId
    ) {
      setErrorMessage(
        t('settings.issuer.taxMissing'),
      )
      setSuccessMessage(null)
      return
    }

    if (
      normalizedIban &&
      !/^[A-Z0-9]{15,34}$/.test(
        normalizedIban,
      )
    ) {
      setErrorMessage(
        t('settings.bank.ibanInvalid'),
      )
      setSuccessMessage(null)
      return
    }

    if (
      normalizedBic &&
      !/^[A-Z0-9]{8}([A-Z0-9]{3})?$/.test(
        normalizedBic,
      )
    ) {
      setErrorMessage(
        t('settings.bank.bicInvalid'),
      )
      setSuccessMessage(null)
      return
    }

    if (
      !/^[A-Z0-9]{1,20}$/.test(
        normalizedNumberPrefix,
      )
    ) {
      setErrorMessage(
        t('settings.invoicePrefixInvalid'),
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
            postal_delivery_fee_net:
              normalizedPostalDeliveryFee,
            billing_start_date:
              billingStartDate || null,
            locale,
            currency,
            default_language: defaultLanguageSetting,
            invoice_payment_term_days:
              paymentTermDays,
            invoice_issuer_name:
              normalizedIssuerName || null,
            invoice_issuer_address:
              normalizedIssuerAddress || null,
            invoice_tax_number:
              normalizedTaxNumber || null,
            invoice_vat_id:
              normalizedVatId || null,
            invoice_bank_name:
              normalizedBankName || null,
            invoice_iban:
              normalizedIban || null,
            invoice_bic:
              normalizedBic || null,
            invoice_issuer_phone:
              normalizedIssuerPhone || null,
            invoice_number_prefix:
              normalizedNumberPrefix,
            invoice_pdf_format:
              invoicePdfFormat,
            invoice_girocode_enabled:
              invoiceGirocodeEnabled,
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
      setPostalDeliveryFeeNet(
        updatedSettings.postal_delivery_fee_net,
      )
      setBillingStartDate(
        updatedSettings.billing_start_date ?? '',
      )
      setLocale(updatedSettings.locale)
      setDefaultLanguageSetting(updatedSettings.default_language)
      setCurrency(updatedSettings.currency)
      setInvoicePaymentTermDays(
        String(
          updatedSettings
            .invoice_payment_term_days,
        ),
      )
      setInvoiceIssuerName(
        updatedSettings.invoice_issuer_name ?? '',
      )
      setInvoiceIssuerAddress(
        updatedSettings.invoice_issuer_address ?? '',
      )
      setInvoiceTaxNumber(
        updatedSettings.invoice_tax_number ?? '',
      )
      setInvoiceVatId(
        updatedSettings.invoice_vat_id ?? '',
      )
      setInvoiceBankName(
        updatedSettings.invoice_bank_name ?? '',
      )
      setInvoiceIban(
        updatedSettings.invoice_iban ?? '',
      )
      setInvoiceBic(
        updatedSettings.invoice_bic ?? '',
      )
      setInvoiceIssuerPhone(
        updatedSettings.invoice_issuer_phone ??
          '',
      )
      setInvoiceNumberPrefix(
        updatedSettings.invoice_number_prefix,
      )
      setInvoicePdfFormat(
        updatedSettings.invoice_pdf_format,
      )
      setInvoiceGirocodeEnabled(
        updatedSettings.invoice_girocode_enabled,
      )

      await refreshSettings()

      setSuccessMessage(
        t('settings.saved'),
      )
    } catch (error) {
      handleRequestError(
        error,
        t('settings.saveFailed'),
      )
    } finally {
      setIsSaving(false)
    }
  }

  return (
    <div className="page admin-page">
      <header className="page-header">
        <div>
          <p className="eyebrow">
            {t('common.administration')}
          </p>

          <h1>{t('settings.title')}</h1>

          <p className="muted">
            {t('settings.intro')}
          </p>
        </div>
      </header>

      {isLoading && (
        <section className="card">
          <p className="muted">
            {t('settings.loading')}
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
            <h2>{t('settings.general.title')}</h2>

            <label className="form-field settings-name-field">
              <span>{t('settings.appName')}</span>

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
                {t('settings.appNameHint')}
              </small>
            </label>

            <label className="form-field">
              <span>{t('settings.defaultLanguage')}</span>

              <select
                value={defaultLanguageSetting}
                onChange={(event) => {
                  setDefaultLanguageSetting(event.target.value)
                }}
              >
                <option value="de">{t('language.de')}</option>
                <option value="en">{t('language.en')}</option>
              </select>

              <small className="muted">
                {t('settings.defaultLanguage.hint')}
              </small>
            </label>

            <label className="form-field settings-name-field">
              <span>{t('settings.girocode')}</span>

              <select
                value={invoiceGirocodeEnabled ? 'yes' : 'no'}
                onChange={(event) => {
                  setInvoiceGirocodeEnabled(
                    event.target.value === 'yes',
                  )
                }}
              >
                <option value="no">{t('common.no')}</option>
                <option value="yes">{t('common.yes')}</option>
              </select>

              <small className="muted">
                {t('settings.girocodeHint')}
              </small>
            </label>
          </section>

          <section className="settings-section">
            <div>
              <h2>{t('settings.issuer.title')}</h2>

              <p className="muted">
                {t('settings.issuer.intro')}
              </p>
            </div>

            <div className="form-grid settings-business-grid">
              <label className="form-field settings-wide-field">
                <span>{t('settings.issuer.name')}</span>

                <input
                  type="text"
                  value={invoiceIssuerName}
                  maxLength={255}
                  onChange={(event) => {
                    setInvoiceIssuerName(
                      event.target.value,
                    )
                  }}
                />
              </label>

              <label className="form-field">
                <span>{t('settings.issuer.address')}</span>

                <textarea
                  rows={3}
                  value={invoiceIssuerAddress}
                  maxLength={500}
                  onChange={(event) => {
                    setInvoiceIssuerAddress(
                      event.target.value,
                    )
                  }}
                />

                <small className="muted">
                  {t('settings.issuer.addressHint')}
                </small>
              </label>

              <label className="form-field">
                <span>{t('settings.issuer.phone')}</span>

                <input
                  type="text"
                  value={invoiceIssuerPhone}
                  maxLength={50}
                  onChange={(event) => {
                    setInvoiceIssuerPhone(
                      event.target.value,
                    )
                  }}
                />

                <small className="muted">
                  {t('settings.issuer.phoneHint')}
                </small>
              </label>

              <label className="form-field">
                <span>{t('settings.issuer.taxNumber')}</span>

                <input
                  type="text"
                  value={invoiceTaxNumber}
                  maxLength={50}
                  onChange={(event) => {
                    setInvoiceTaxNumber(
                      event.target.value,
                    )
                  }}
                />
              </label>

              <label className="form-field">
                <span>{t('settings.issuer.vatId')}</span>

                <input
                  type="text"
                  value={invoiceVatId}
                  maxLength={50}
                  onChange={(event) => {
                    setInvoiceVatId(
                      event.target.value,
                    )
                  }}
                />
              </label>
            </div>
          </section>

          <section className="settings-section">
            <div>
              <h2>{t('settings.bank.title')}</h2>

              <p className="muted">
                {t('settings.bank.intro')}
              </p>
            </div>

            <div className="form-grid settings-business-grid">
              <label className="form-field settings-wide-field">
                <span>{t('settings.bank.name')}</span>

                <input
                  type="text"
                  value={invoiceBankName}
                  maxLength={255}
                  onChange={(event) => {
                    setInvoiceBankName(
                      event.target.value,
                    )
                  }}
                />
              </label>

              <label className="form-field">
                <span>{t('settings.bank.iban')}</span>

                <input
                  type="text"
                  value={invoiceIban}
                  maxLength={42}
                  autoComplete="off"
                  onChange={(event) => {
                    setInvoiceIban(
                      event.target.value,
                    )
                  }}
                />

                <small className="muted">
                  {t('settings.bank.ibanHint')}
                </small>
              </label>

              <label className="form-field">
                <span>{t('settings.bank.bic')}</span>

                <input
                  type="text"
                  value={invoiceBic}
                  maxLength={11}
                  autoComplete="off"
                  onChange={(event) => {
                    setInvoiceBic(
                      event.target.value,
                    )
                  }}
                />
              </label>
            </div>
          </section>

          <h2>{t('settings.billing.title')}</h2>

          <div className="form-grid settings-billing-grid">
            <label className="form-field">
              <span>{t('settings.locale')}</span>

              <select
                value={locale}
                onChange={(event) => {
                  setLocale(event.target.value)
                }}
              >
                <option value="de-DE">{t('settings.locale.deDE')}</option>
                <option value="de-AT">{t('settings.locale.deAT')}</option>
                <option value="de-CH">{t('settings.locale.deCH')}</option>
                <option value="en-GB">{t('settings.locale.enGB')}</option>
                <option value="en-US">{t('settings.locale.enUS')}</option>
              </select>

              <small className="muted">
                {t('settings.localeHint')}
              </small>
            </label>

            <label className="form-field">
              <span>{t('settings.currency')}</span>

              <select
                value={currency}
                onChange={(event) => {
                  setCurrency(event.target.value)
                }}
              >
                <option value="EUR">{t('settings.currency.EUR')}</option>
                <option value="CHF">{t('settings.currency.CHF')}</option>
                <option value="GBP">{t('settings.currency.GBP')}</option>
                <option value="USD">{t('settings.currency.USD')}</option>
              </select>

              <small className="muted">
                {t('settings.currencyHint')}
              </small>
            </label>

            <label className="form-field">
              <span>{t('settings.billingStart')}</span>

              <input
                type="date"
                value={billingStartDate}
                onChange={(event) => {
                  setBillingStartDate(
                    event.target.value,
                  )
                }}
              />

              <small className="muted">
                {t('settings.billingStartHint')}
              </small>
            </label>

              <label className="form-field">
              <span>
                {t('settings.baseFee')}
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
                {t('settings.baseFeeHint')}
              </small>
              </label>

            <label className="form-field">
              <span>
                {t('settings.baseFeeVat')}
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
              <span>{t('settings.postalFee')}</span>

              <input
                type="text"
                inputMode="decimal"
                value={postalDeliveryFeeNet}
                onChange={(event) => {
                  setPostalDeliveryFeeNet(
                    event.target.value,
                  )
                }}
                required
              />

              <small className="muted">
                {t('settings.postalFeeHint')}
              </small>
            </label>

            <label className="form-field">
              <span>
                {t('settings.paymentTerm')}
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
                {t('settings.paymentTermHint')}
              </small>
            </label>

              <label className="form-field">
                <span>
                  {t('settings.invoicePrefix')}
                </span>

                <input
                  type="text"
                  value={invoiceNumberPrefix}
                  maxLength={20}
                  onChange={(event) => {
                    setInvoiceNumberPrefix(
                      event.target.value,
                    )
                  }}
                  required
                />

                <small className="muted">
                  {t('settings.invoicePrefixHint')}
                </small>
              </label>

              <label className="form-field">
                <span>{t('settings.pdfFormat')}</span>

                <select
                  value={invoicePdfFormat}
                  onChange={(event) => {
                    setInvoicePdfFormat(
                      event.target.value as
                        | 'standard'
                        | 'pdfa-2b',
                    )
                  }}
                >
                  <option value="standard">
                    {t('settings.pdfFormat.standard')}
                  </option>

                  <option value="pdfa-2b">
                    {t('settings.pdfFormat.pdfa')}
                  </option>
                </select>

                <small className="muted">
                  {t('settings.pdfFormatHint')}
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
                ? t('settings.saving')
                : t('settings.save')}
            </button>
          </div>
        </form>
      )}
      {!isLoading && (
        <AdminEnergyPricesForm />
      )}
      {!isLoading && (
        <AdminAccessSettingsForm />
      )}
      {!isLoading && (
        <AdminPasswordPolicyForm />
      )}
      {!isLoading && (
        <AdminHagerSettingsForm />
      )}

      {!isLoading && (
        <AdminWallboxesForm />
      )}
      {!isLoading && (
        <AdminInvoiceExportSettingsForm />
      )}
      {!isLoading && (
        <AdminSmtpSettingsForm />
      )}
    </div>
  )
}

export default AdminSettingsPage
