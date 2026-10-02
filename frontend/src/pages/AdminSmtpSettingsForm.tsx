import {
  type FormEvent,
  useCallback,
  useEffect,
  useState,
} from 'react'
import { useNavigate } from 'react-router-dom'

import {
  getSmtpSettings,
  SettingsApiError,
  testSmimeSettings,
  testSmtpSettings,
  updateSmtpSettings,
} from '../api/settings'

import { getAccessToken } from '../auth/tokenStorage'
import { useAuth } from '../auth/useAuth'
import { useTranslation } from '../i18n/useTranslation'

const MAX_SMIME_FILE_SIZE = 65535

async function fileToBase64(
  file: File,
): Promise<string> {
  const bytes = new Uint8Array(
    await file.arrayBuffer(),
  )
  let binary = ''

  for (const byte of bytes) {
    binary += String.fromCharCode(byte)
  }

  return window.btoa(binary)
}

function AdminSmtpSettingsForm() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const { signOut } = useAuth()

  const [
    useDatabaseSettings,
    setUseDatabaseSettings,
  ] = useState(false)
  const [
    mailSendingEnabled,
    setMailSendingEnabled,
  ] = useState(true)
  const [smtpHost, setSmtpHost] = useState('')
  const [smtpPort, setSmtpPort] = useState('')
  const [
    smtpTimeoutSeconds,
    setSmtpTimeoutSeconds,
  ] = useState('')
  const [smtpStarttls, setSmtpStarttls] =
    useState(false)
  const [smtpUsername, setSmtpUsername] =
    useState('')
  const [smtpPassword, setSmtpPassword] =
    useState('')
  const [
    smtpPasswordConfigured,
    setSmtpPasswordConfigured,
  ] = useState(false)
  const [
    clearSmtpPassword,
    setClearSmtpPassword,
  ] = useState(false)
  const [
    mailFromAddress,
    setMailFromAddress,
  ] = useState('')
  const [mailFromName, setMailFromName] =
    useState('')
  const [smimeEnabled, setSmimeEnabled] =
    useState(false)
  const [smimeCertificateFile, setSmimeCertificateFile] =
    useState<File | null>(null)
  const [smimeCertificateConfigured, setSmimeCertificateConfigured] =
    useState(false)
  const [smimeCertificateFilename, setSmimeCertificateFilename] =
    useState<string | null>(null)
  const [smimeCertificateSource, setSmimeCertificateSource] =
    useState<'upload' | 'environment' | null>(null)
  const [smimePassword, setSmimePassword] =
    useState('')
  const [smimePasswordConfigured, setSmimePasswordConfigured] =
    useState(false)
  const [clearSmimeCertificate, setClearSmimeCertificate] =
    useState(false)
  const [smimeFileInputKey, setSmimeFileInputKey] =
    useState(0)

  const [isLoading, setIsLoading] =
    useState(true)
  const [isSaving, setIsSaving] =
    useState(false)
  const [isTesting, setIsTesting] =
    useState(false)
  const [isTestingSmime, setIsTestingSmime] =
    useState(false)
  const [
    errorMessage,
    setErrorMessage,
  ] = useState<string | null>(null)
  const [
    successMessage,
    setSuccessMessage,
  ] = useState<string | null>(null)

  const handleUnauthorized = useCallback((): void => {
    signOut()

    navigate('/login', {
      replace: true,
    })
  }, [navigate, signOut])

  useEffect(() => {
    const controller = new AbortController()

    async function loadSettings(): Promise<void> {
      const accessToken = getAccessToken()

      if (accessToken === null) {
        handleUnauthorized()
        return
      }

      setIsLoading(true)
      setErrorMessage(null)

      try {
        const loadedSettings =
          await getSmtpSettings(
            accessToken,
            controller.signal,
          )

        setUseDatabaseSettings(
          loadedSettings
            .smtp_use_database_settings,
        )
        setMailSendingEnabled(
          loadedSettings.mail_sending_enabled,
        )
        setSmtpHost(loadedSettings.smtp_host)
        setSmtpPort(
          String(loadedSettings.smtp_port),
        )
        setSmtpTimeoutSeconds(
          loadedSettings.smtp_timeout_seconds,
        )
        setSmtpStarttls(
          loadedSettings.smtp_starttls,
        )
        setSmtpUsername(
          loadedSettings.smtp_username ?? '',
        )
        setSmtpPasswordConfigured(
          loadedSettings
            .smtp_password_configured,
        )
        setMailFromAddress(
          loadedSettings.mail_from_address,
        )
        setMailFromName(
          loadedSettings.mail_from_name,
        )
        setSmimeEnabled(
          loadedSettings.mail_smime_enabled,
        )
        setSmimeCertificateConfigured(
          loadedSettings
            .smime_certificate_configured,
        )
        setSmimeCertificateFilename(
          loadedSettings
            .smime_certificate_filename,
        )
        setSmimeCertificateSource(
          loadedSettings
            .smime_certificate_source,
        )
        setSmimePasswordConfigured(
          loadedSettings
            .smime_password_configured,
        )
      } catch (error) {
        if (
          error instanceof DOMException &&
          error.name === 'AbortError'
        ) {
          return
        }

        if (
          error instanceof SettingsApiError &&
          error.status === 401
        ) {
          handleUnauthorized()
          return
        }

        setErrorMessage(
          error instanceof Error
            ? error.message
            : t('settings.smtp.loadFailed'),
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
  }, [handleUnauthorized])

  async function handleSubmit(
    event: FormEvent<HTMLFormElement>,
  ): Promise<void> {
    event.preventDefault()

    const normalizedHost = smtpHost.trim()
    const normalizedUsername =
      smtpUsername.trim()
    const normalizedFromAddress =
      mailFromAddress.trim()
    const normalizedFromName =
      mailFromName.trim()
    const port = Number(smtpPort)
    const timeout = Number(
      smtpTimeoutSeconds
        .trim()
        .replace(',', '.'),
    )

    setErrorMessage(null)
    setSuccessMessage(null)

    if (useDatabaseSettings) {
      if (!normalizedHost) {
        setErrorMessage(
          t('settings.smtp.hostMissing'),
        )
        return
      }

      if (
        !Number.isInteger(port) ||
        port < 1 ||
        port > 65535
      ) {
        setErrorMessage(
          t('settings.smtp.portRange'),
        )
        return
      }

      if (
        !Number.isFinite(timeout) ||
        timeout <= 0 ||
        timeout > 300
      ) {
        setErrorMessage(
          t('settings.smtp.timeoutRange'),
        )
        return
      }

      if (!normalizedFromName) {
        setErrorMessage(
          t('settings.smtp.senderNameMissing'),
        )
        return
      }

      if (
        !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(
          normalizedFromAddress,
        )
      ) {
        setErrorMessage(
          t('settings.smtp.senderAddressInvalid'),
        )
        return
      }

      if (
        normalizedUsername &&
        !smtpPasswordConfigured &&
        !smtpPassword
      ) {
        setErrorMessage(
          t('settings.smtp.passwordRequired'),
        )
        return
      }
    }

    if (
      smimeCertificateFile !== null &&
      smimeCertificateFile.size >
        MAX_SMIME_FILE_SIZE
    ) {
      setErrorMessage(
        t('settings.smime.fileTooLarge'),
      )
      return
    }

    if (
      smimeCertificateFile !== null &&
      !smimePassword &&
      !(
        smimePasswordConfigured &&
        smimeCertificateSource === 'upload'
      )
    ) {
      setErrorMessage(
        t('settings.smime.passwordRequired'),
      )
      return
    }

    if (
      smimePassword &&
      smimeCertificateFile === null &&
      smimeCertificateSource !== 'upload'
    ) {
      setErrorMessage(
        t('settings.smime.fileRequired'),
      )
      return
    }

    if (
      smimeEnabled &&
      !smimeCertificateConfigured &&
      smimeCertificateFile === null
    ) {
      setErrorMessage(
        t('settings.smime.uploadRequired'),
      )
      return
    }

    const accessToken = getAccessToken()

    if (accessToken === null) {
      handleUnauthorized()
      return
    }

    setIsSaving(true)

    try {
      const smimePkcs12Base64 =
        smimeCertificateFile === null
          ? null
          : await fileToBase64(
              smimeCertificateFile,
            )

      const updatedSettings =
        await updateSmtpSettings(
          accessToken,
          {
            smtp_use_database_settings:
              useDatabaseSettings,
            mail_sending_enabled:
              mailSendingEnabled,
            smtp_host: normalizedHost,
            smtp_port: port,
            smtp_timeout_seconds:
              String(timeout),
            smtp_starttls: smtpStarttls,
            smtp_username:
              normalizedUsername || null,
            ...(smtpPassword
              ? {
                  smtp_password:
                    smtpPassword,
                }
              : {}),
            clear_smtp_password:
              clearSmtpPassword,
            mail_from_address:
              normalizedFromAddress,
            mail_from_name:
              normalizedFromName,
            mail_smime_enabled: smimeEnabled,
            ...(smimePkcs12Base64 !== null &&
            smimeCertificateFile !== null
              ? {
                  smime_pkcs12_base64:
                    smimePkcs12Base64,
                  smime_pkcs12_filename:
                    smimeCertificateFile.name,
                }
              : {}),
            ...(smimePassword
              ? {
                  smime_password:
                    smimePassword,
                }
              : {}),
            clear_smime_certificate:
              clearSmimeCertificate,
          },
        )

      setUseDatabaseSettings(
        updatedSettings
          .smtp_use_database_settings,
      )
      setMailSendingEnabled(
        updatedSettings.mail_sending_enabled,
      )
      setSmtpHost(updatedSettings.smtp_host)
      setSmtpPort(
        String(updatedSettings.smtp_port),
      )
      setSmtpTimeoutSeconds(
        updatedSettings.smtp_timeout_seconds,
      )
      setSmtpStarttls(
        updatedSettings.smtp_starttls,
      )
      setSmtpUsername(
        updatedSettings.smtp_username ?? '',
      )
      setSmtpPassword('')
      setSmtpPasswordConfigured(
        updatedSettings
          .smtp_password_configured,
      )
      setClearSmtpPassword(false)
      setMailFromAddress(
        updatedSettings.mail_from_address,
      )
      setMailFromName(
        updatedSettings.mail_from_name,
      )
      setSmimeEnabled(
        updatedSettings.mail_smime_enabled,
      )
      setSmimeCertificateFile(null)
      setSmimeCertificateConfigured(
        updatedSettings
          .smime_certificate_configured,
      )
      setSmimeCertificateFilename(
        updatedSettings
          .smime_certificate_filename,
      )
      setSmimeCertificateSource(
        updatedSettings
          .smime_certificate_source,
      )
      setSmimePassword('')
      setSmimePasswordConfigured(
        updatedSettings
          .smime_password_configured,
      )
      setClearSmimeCertificate(false)
      setSmimeFileInputKey((key) => key + 1)

      setSuccessMessage(
        t('settings.smtp.saved'),
      )
    } catch (error) {
      if (
        error instanceof SettingsApiError &&
        error.status === 401
      ) {
        handleUnauthorized()
        return
      }

      setErrorMessage(
        error instanceof Error
          ? error.message
          : t('settings.smtp.saveFailed'),
      )
    } finally {
      setIsSaving(false)
    }
  }

  async function handleTest(): Promise<void> {
    const accessToken = getAccessToken()

    if (accessToken === null) {
      handleUnauthorized()
      return
    }

    setIsTesting(true)
    setErrorMessage(null)
    setSuccessMessage(null)

    try {
      const result = await testSmtpSettings(
        accessToken,
      )

      setSuccessMessage(
        t('settings.smtp.testSent', { email: result.recipient_email }),
      )
    } catch (error) {
      if (
        error instanceof SettingsApiError &&
        error.status === 401
      ) {
        handleUnauthorized()
        return
      }

      setErrorMessage(
        error instanceof Error
          ? error.message
          : t('settings.smtp.testFailed'),
      )
    } finally {
      setIsTesting(false)
    }
  }

  async function handleSmimeTest(): Promise<void> {
    const accessToken = getAccessToken()

    if (accessToken === null) {
      handleUnauthorized()
      return
    }

    setIsTestingSmime(true)
    setErrorMessage(null)
    setSuccessMessage(null)

    try {
      const result = await testSmimeSettings(
        accessToken,
      )

      setSuccessMessage(
        t('settings.smime.testSent', { email: result.recipient_email }),
      )
    } catch (error) {
      if (
        error instanceof SettingsApiError &&
        error.status === 401
      ) {
        handleUnauthorized()
        return
      }

      setErrorMessage(
        error instanceof Error
          ? error.message
          : t('settings.smime.testFailed'),
      )
    } finally {
      setIsTestingSmime(false)
    }
  }

  if (isLoading) {
    return (
      <section className="card">
        <p className="muted">
          {t('settings.smtp.loading')}
        </p>
      </section>
    )
  }

  return (
    <form
      className="card settings-form"
      onSubmit={handleSubmit}
    >
      <section className="settings-section">
        <div>
          <h2>{t('settings.smtp.title')}</h2>

          <p className="muted">
            {t('settings.smtp.intro')}
          </p>
        </div>

        {errorMessage && (
          <div
            className="form-error"
            role="alert"
          >
            {errorMessage}
          </div>
        )}

        {successMessage && (
          <div
            className="form-success"
            role="status"
          >
            {successMessage}
          </div>
        )}

        <div className="form-grid settings-business-grid">
          <label className="form-field">
            <span>{t('settings.smtp.source')}</span>

            <select
              value={
                useDatabaseSettings
                  ? 'database'
                  : 'environment'
              }
              onChange={(event) => {
                setUseDatabaseSettings(
                  event.target.value ===
                    'database',
                )
              }}
            >
              <option value="environment">
                {t('settings.smtp.source.environment')}
              </option>
              <option value="database">
                {t('settings.smtp.source.database')}
              </option>
            </select>
          </label>

          <label className="form-field settings-checkbox-field">
            <span>{t('settings.smtp.sending')}</span>

            <span className="settings-checkbox-control">
              <input
                type="checkbox"
                checked={mailSendingEnabled}
                onChange={(event) => {
                  setMailSendingEnabled(
                    event.target.checked,
                  )
                }}
              />

              {t('settings.smtp.sendingEnabled')}
            </span>
          </label>

          <label className="form-field">
            <span>{t('settings.smtp.host')}</span>

            <input
              type="text"
              value={smtpHost}
              maxLength={255}
              disabled={!useDatabaseSettings}
              onChange={(event) => {
                setSmtpHost(event.target.value)
              }}
              required={useDatabaseSettings}
            />
          </label>

          <label className="form-field">
            <span>{t('settings.smtp.port')}</span>

            <input
              type="number"
              min="1"
              max="65535"
              step="1"
              value={smtpPort}
              disabled={!useDatabaseSettings}
              onChange={(event) => {
                setSmtpPort(event.target.value)
              }}
              required={useDatabaseSettings}
            />
          </label>

          <label className="form-field">
            <span>{t('settings.smtp.timeout')}</span>

            <input
              type="text"
              inputMode="decimal"
              value={smtpTimeoutSeconds}
              disabled={!useDatabaseSettings}
              onChange={(event) => {
                setSmtpTimeoutSeconds(
                  event.target.value,
                )
              }}
              required={useDatabaseSettings}
            />
          </label>

          <label className="form-field settings-checkbox-field">
            <span>{t('settings.smtp.encryption')}</span>

            <span className="settings-checkbox-control">
              <input
                type="checkbox"
                checked={smtpStarttls}
                disabled={!useDatabaseSettings}
                onChange={(event) => {
                  setSmtpStarttls(
                    event.target.checked,
                  )
                }}
              />

              {t('settings.smtp.starttls')}
            </span>
          </label>

          <label className="form-field">
            <span>{t('settings.smtp.username')}</span>

            <input
              type="text"
              value={smtpUsername}
              maxLength={255}
              autoComplete="username"
              disabled={!useDatabaseSettings}
              onChange={(event) => {
                setSmtpUsername(
                  event.target.value,
                )
              }}
            />
          </label>

          <div className="form-field settings-password-field">
            <span id="smtp-password-label">
              {t('settings.smtp.password')}
            </span>

            <input
              type="password"
              value={smtpPassword}
              aria-labelledby="smtp-password-label"
              autoComplete="new-password"
              disabled={
                !useDatabaseSettings ||
                clearSmtpPassword
              }
              onChange={(event) => {
                setSmtpPassword(
                  event.target.value,
                )
              }}
            />

            <small className="muted">
              {smtpPasswordConfigured
                ? t('settings.hager.passwordStored')
                : t('settings.hager.passwordMissing')}
            </small>

            <label className="settings-checkbox-control settings-password-clear-control">
              <input
                type="checkbox"
                checked={clearSmtpPassword}
                disabled={
                  !useDatabaseSettings ||
                  !smtpPasswordConfigured
                }
                onChange={(event) => {
                  setClearSmtpPassword(
                    event.target.checked,
                  )

                  if (event.target.checked) {
                    setSmtpPassword('')
                  }
                }}
              />

              {t('settings.hager.clearPassword')}
            </label>
          </div>

          <label className="form-field settings-smtp-sender-field">
            <span>{t('settings.smtp.senderName')}</span>

            <input
              type="text"
              value={mailFromName}
              maxLength={255}
              disabled={!useDatabaseSettings}
              onChange={(event) => {
                setMailFromName(
                  event.target.value,
                )
              }}
              required={useDatabaseSettings}
            />
          </label>

          <label className="form-field">
            <span>{t('settings.smtp.senderAddress')}</span>

            <input
              type="email"
              value={mailFromAddress}
              maxLength={320}
              autoComplete="email"
              disabled={!useDatabaseSettings}
              onChange={(event) => {
                setMailFromAddress(
                  event.target.value,
                )
              }}
              required={useDatabaseSettings}
            />
          </label>
        </div>
      </section>

      <section className="settings-section settings-smime-section">
        <div>
          <h2>{t('settings.smime.title')}</h2>

          <p className="muted">
            {t('settings.smime.intro')}
          </p>
        </div>

        <div className="form-grid settings-business-grid">
          <label className="form-field settings-checkbox-field">
            <span>{t('settings.smime.sending')}</span>

            <span className="settings-checkbox-control">
              <input
                type="checkbox"
                checked={smimeEnabled}
                onChange={(event) => {
                  setSmimeEnabled(
                    event.target.checked,
                  )
                }}
              />

              {t('settings.smime.enable')}
            </span>
          </label>

          <label className="form-field settings-smime-file-field">
            <span>{t('settings.smime.certificate')}</span>

            <input
              key={smimeFileInputKey}
              type="file"
              accept=".p12,.pfx,application/x-pkcs12"
              disabled={clearSmimeCertificate}
              onChange={(event) => {
                const file =
                  event.target.files?.[0] ?? null

                setSmimeCertificateFile(file)

                if (file !== null) {
                  setClearSmimeCertificate(false)
                }
              }}
            />

            <small className="muted">
              {smimeCertificateConfigured
                ? t(
                    smimeCertificateSource === 'environment'
                      ? 'settings.smime.configuredEnvironment'
                      : 'settings.smime.configured',
                    {
                      name:
                        smimeCertificateFilename ??
                        t('settings.smime.aCertificate'),
                    },
                  )
                : t('settings.smime.notConfigured')}
            </small>
          </label>

          <div className="form-field settings-password-field">
            <span id="smime-password-label">
              {t('settings.smime.password')}
            </span>

            <input
              type="password"
              value={smimePassword}
              aria-labelledby="smime-password-label"
              autoComplete="new-password"
              disabled={clearSmimeCertificate}
              onChange={(event) => {
                setSmimePassword(
                  event.target.value,
                )
              }}
            />

            <small className="muted">
              {smimePasswordConfigured
                ? t('settings.smime.passwordConfigured')
                : t('settings.smime.passwordFirstUpload')}
            </small>

            <label className="settings-checkbox-control settings-password-clear-control">
              <input
                type="checkbox"
                checked={clearSmimeCertificate}
                disabled={
                  smimeCertificateSource !== 'upload'
                }
                onChange={(event) => {
                  const shouldClear =
                    event.target.checked

                  setClearSmimeCertificate(
                    shouldClear,
                  )

                  if (shouldClear) {
                    setSmimeCertificateFile(null)
                    setSmimePassword('')
                    setSmimeFileInputKey(
                      (key) => key + 1,
                    )
                  }
                }}
              />

              {t('settings.smime.clear')}
            </label>
          </div>
        </div>

        <p className="settings-security-warning" role="note">
          {t('settings.smime.securityHint')}
        </p>
      </section>

      <div className="settings-actions">
        <button
          className="button button-primary"
          type="submit"
          disabled={
            isSaving ||
            isTesting ||
            isTestingSmime
          }
        >
          {isSaving
            ? t('settings.smtp.saving')
            : t('settings.smtp.save')}
        </button>

        <button
          className="button"
          type="button"
          disabled={
            isSaving ||
            isTesting ||
            isTestingSmime
          }
          onClick={() => {
            void handleTest()
          }}
        >
          {isTesting
            ? t('settings.smtp.testing')
            : t('settings.smtp.test')}
        </button>

        <button
          className="button"
          type="button"
          disabled={
            isSaving ||
            isTesting ||
            isTestingSmime
          }
          onClick={() => {
            void handleSmimeTest()
          }}
        >
          {isTestingSmime
            ? t('settings.smime.testing')
            : t('settings.smime.test')}
        </button>
      </div>

      <p className="muted">
        {t('settings.smtp.testHint')}
      </p>
    </form>
  )
}

export default AdminSmtpSettingsForm
