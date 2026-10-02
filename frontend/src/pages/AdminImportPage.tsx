import {
  type ChangeEvent,
  type FormEvent,
  useState,
} from 'react'
import { useNavigate } from 'react-router-dom'

import {
  getImportFileType,
  ImportApiError,
  importFromHager,
  type HagerImportRequest,
  type ImportResult,
  uploadImportFile,
} from '../api/imports'
import { getAccessToken } from '../auth/tokenStorage'
import { useAuth } from '../auth/useAuth'
import type { I18nContextValue } from '../i18n/i18nContext'
import { formatDate } from '../utils/dateFormat'
import { formatNumber } from '../utils/numberFormat'
import { useTranslation } from '../i18n/useTranslation'

const MAX_UPLOAD_SIZE_BYTES =
  10 * 1024 * 1024

type Translate = I18nContextValue['t']


function validateFile(
  file: File,
  t: Translate,
): string | null {
  if (getImportFileType(file.name) === null) {
    return t('import.file.invalidType')
  }

  if (file.size === 0) {
    return t('import.file.empty')
  }

  if (file.size > MAX_UPLOAD_SIZE_BYTES) {
    return t('import.file.tooLarge')
  }

  return null
}




interface RfidIssueGroup {
  title: string
  hint: string
  numbers: string[]
}

function rfidIssueGroups(
  result: ImportResult,
  t: Translate,
): RfidIssueGroup[] {
  const hasDetails =
    result.unknown_rfid_cards !== undefined ||
    result.inactive_rfid_cards !== undefined ||
    result.unassigned_rfid_numbers !== undefined

  if (!hasDetails) {
    return [
      {
        title: t('import.issue.none.title'),
        hint: t('import.issue.none.hint'),
        numbers: result.unknown_rfid_numbers,
      },
    ]
  }

  const groups: RfidIssueGroup[] = [
    {
      title: t('import.issue.noAssignment.title'),
      hint: t('import.issue.noAssignment.hint'),
      numbers: result.unassigned_rfid_numbers ?? [],
    },
    {
      title: t('import.issue.inactive.title'),
      hint: t('import.issue.inactive.hint'),
      numbers: result.inactive_rfid_cards ?? [],
    },
    {
      title: t('import.issue.unknown.title'),
      hint: t('import.issue.unknown.hint'),
      numbers: result.unknown_rfid_cards ?? [],
    },
  ]

  return groups.filter((group) => group.numbers.length > 0)
}


function formatFileSize(
  sizeBytes: number,
): string {
  return `${formatNumber(sizeBytes / 1024 / 1024, 2)} MB`
}

function AdminImportPage() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const { signOut } = useAuth()

  const [
    selectedFile,
    setSelectedFile,
  ] = useState<File | null>(null)

  const [
    importResult,
    setImportResult,
  ] = useState<ImportResult | null>(null)

  const [
    errorMessage,
    setErrorMessage,
  ] = useState<string | null>(null)

  const [
    isUploading,
    setIsUploading,
  ] = useState(false)

  const [
    isFetchingHager,
    setIsFetchingHager,
  ] = useState(false)

  const [hagerFrom, setHagerFrom] = useState('')
  const [hagerTo, setHagerTo] = useState('')
  const [hagerFetchAll, setHagerFetchAll] = useState(false)
  const [resultFromHager, setResultFromHager] = useState(false)

  const isBusy = isUploading || isFetchingHager

  function handleFileChange(
    event: ChangeEvent<HTMLInputElement>,
  ): void {
    const file =
      event.target.files?.[0] ?? null

    setErrorMessage(null)
    setImportResult(null)

    if (file === null) {
      setSelectedFile(null)
      return
    }

    const validationError =
      validateFile(file, t)

    if (validationError !== null) {
      setSelectedFile(null)
      setErrorMessage(validationError)

      event.target.value = ''
      return
    }

    setSelectedFile(file)
  }

  async function handleSubmit(
    event: FormEvent<HTMLFormElement>,
  ): Promise<void> {
    event.preventDefault()

    setErrorMessage(null)
    setImportResult(null)

    if (selectedFile === null) {
      setErrorMessage(
        t('import.file.missing'),
      )
      return
    }

    const validationError =
      validateFile(selectedFile, t)

    if (validationError !== null) {
      setErrorMessage(validationError)
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

    setIsUploading(true)

    try {
      const result = await uploadImportFile(
        accessToken,
        selectedFile,
      )

      setImportResult(result)
      setResultFromHager(false)
    } catch (error) {
      if (
        error instanceof ImportApiError &&
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
          : t('import.file.failed'),
      )
    } finally {
      setIsUploading(false)
    }
  }

  async function handleHagerImport(
    event: FormEvent<HTMLFormElement>,
  ): Promise<void> {
    event.preventDefault()

    setErrorMessage(null)
    setImportResult(null)

    if (hagerFrom && hagerTo && hagerFrom > hagerTo) {
      setErrorMessage(
        t('import.hager.rangeInvalid'),
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

    const payload: HagerImportRequest = {}

    if (hagerFetchAll) {
      payload.fetch_all = true
    } else {
      if (hagerFrom) {
        payload.date_from = hagerFrom
      }

      if (hagerTo) {
        payload.date_to = hagerTo
      }
    }

    setIsFetchingHager(true)

    try {
      setImportResult(
        await importFromHager(
          accessToken,
          payload,
        ),
      )
      setResultFromHager(true)
    } catch (error) {
      if (
        error instanceof ImportApiError &&
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
          : t('import.hager.failed'),
      )
    } finally {
      setIsFetchingHager(false)
    }
  }

  return (
    <div className="page admin-page">
      <header className="page-header">
        <div>
          <p className="eyebrow">
            {t('common.administration')}
          </p>

          <h1>{t('import.title')}</h1>

          <p className="muted">
            {t('import.intro')}
          </p>
        </div>
      </header>

      {errorMessage && (
        <section
          className="card form-error admin-message"
          role="alert"
        >
          {errorMessage}
        </section>
      )}

      <form
        className="card import-form"
        onSubmit={handleHagerImport}
      >
        <div>
          <h2>{t('import.hager.title')}</h2>

          <p className="muted">
            {t('import.hager.intro')}
          </p>
        </div>

        <div className="form-grid">
          <label className="form-field">
            <span>{t('import.hager.from')}</span>
            <input
              type="date"
              value={hagerFrom}
              disabled={isBusy || hagerFetchAll}
              onChange={(event) => {
                setHagerFrom(event.target.value)
              }}
            />
          </label>

          <label className="form-field">
            <span>{t('import.hager.to')}</span>
            <input
              type="date"
              value={hagerTo}
              disabled={isBusy || hagerFetchAll}
              onChange={(event) => {
                setHagerTo(event.target.value)
              }}
            />
          </label>
        </div>

        <label className="settings-checkbox-control">
          <input
            type="checkbox"
            checked={hagerFetchAll}
            disabled={isBusy}
            onChange={(event) => {
              setHagerFetchAll(event.target.checked)
            }}
          />
          {t('import.hager.all')}
        </label>

        <div className="form-actions">
          <button
            className="button button-primary"
            type="submit"
            disabled={isBusy}
          >
            {isFetchingHager
              ? t('import.hager.submitting')
              : t('import.hager.submit')}
          </button>
        </div>
      </form>

      <form
        className="card import-form"
        onSubmit={handleSubmit}
      >
        <div>
          <h2>{t('import.file.title')}</h2>

          <p className="muted">
            {t('import.file.intro')}
          </p>
        </div>

        <label className="form-field">
          <span>{t('import.file.choose')}</span>

          <input
            type="file"
            accept={
              '.xlsx,.json,' +
              'application/vnd.openxmlformats-' +
              'officedocument.spreadsheetml.sheet,' +
              'application/json'
            }
            disabled={isBusy}
            onChange={handleFileChange}
          />
        </label>

        {selectedFile !== null && (
          <div className="import-file-summary">
            <strong>
              {selectedFile.name}
            </strong>

            <span>
              {formatFileSize(
                selectedFile.size,
              )}
            </span>
          </div>
        )}

        <div className="form-actions">
          <button
            className="button button-primary"
            type="submit"
            disabled={
              isBusy ||
              selectedFile === null
            }
          >
            {isUploading
              ? t('import.file.submitting')
              : t('import.file.submit')}
          </button>
        </div>
      </form>

      {importResult !== null && (
        <section
          className="card import-result"
          aria-live="polite"
        >
          <div className="import-result-header">
            <p className="eyebrow">
              {t('import.result.eyebrow')}
            </p>

            <h2>{t('import.result.title')}</h2>
          </div>

          <dl className="import-result-grid">
            <div>
              <dt>{t('import.result.read')}</dt>
              <dd>{importResult.read}</dd>
            </div>

            <div>
              <dt>{t('import.result.imported')}</dt>
              <dd>{importResult.imported}</dd>
            </div>

            <div>
              <dt>{t('import.result.skipped')}</dt>
              <dd>{importResult.skipped}</dd>
            </div>

            <div>
              <dt>{t('import.result.priced')}</dt>
              <dd>{importResult.priced}</dd>
            </div>

            <div>
              <dt>{t('import.result.missingPrice')}</dt>
              <dd>
                {importResult.missing_price}
              </dd>
            </div>

            <div>
              <dt>{t('import.result.invalidEnergy')}</dt>
              <dd>
                {importResult.invalid_energy}
              </dd>
            </div>

            <div>
              <dt>
                {t('import.result.unassigned')}
              </dt>
              <dd>
                {
                  importResult
                    .unknown_rfid_sessions
                }
              </dd>
            </div>
          </dl>

          {resultFromHager && (
            <p className="muted">
              {importResult.fetched_from
                ? t('import.result.fetchedFrom', {
                    date: formatDate(importResult.fetched_from),
                  })
                : t('import.result.fetchedAll')}
            </p>
          )}

          {((importResult.skipped_before_billing_start ?? 0) > 0 ||
            (importResult.skipped_empty ?? 0) > 0) && (
            <p className="muted">
              {t('import.result.notTaken', {
                items: [
                  (importResult.skipped_before_billing_start ?? 0) > 0
                    ? t('import.result.beforeBillingStart', {
                        count: importResult.skipped_before_billing_start ?? 0,
                      })
                    : null,
                  (importResult.skipped_empty ?? 0) > 0
                    ? t('import.result.withoutEnergy', {
                        count: importResult.skipped_empty ?? 0,
                      })
                    : null,
                ]
                  .filter(Boolean)
                  .join(', '),
              })}
            </p>
          )}

          {(importResult.reassigned_sessions ?? 0) > 0 && (
            <p className="form-success" role="status">
              {t('import.result.reassigned', {
                count: importResult.reassigned_sessions ?? 0,
              })}
            </p>
          )}

          {importResult
            .unknown_rfid_numbers
            .length > 0 && (
            <div className="import-warning">
              <h3>
                {t('import.result.unassignedTitle')}
              </h3>

              <p>
                {t('import.result.unassignedText', {
                  count: importResult.unknown_rfid_sessions,
                })}{' '}
                {t('import.result.unassignedHint')}
              </p>

              {rfidIssueGroups(importResult, t).map(
                (group) => (
                  <div key={group.title}>
                    <h4>{group.title}</h4>
                    <p className="muted">
                      {group.hint}
                    </p>
                    <ul>
                      {group.numbers.map(
                        (rfidNumber) => (
                          <li key={rfidNumber}>
                            {rfidNumber}
                          </li>
                        ),
                      )}
                    </ul>
                  </div>
                ),
              )}
            </div>
          )}
        </section>
      )}
    </div>
  )
}

export default AdminImportPage
