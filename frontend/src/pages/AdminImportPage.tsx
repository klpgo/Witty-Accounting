import {
  type ChangeEvent,
  type FormEvent,
  useState,
} from 'react'
import { useNavigate } from 'react-router-dom'

import {
  ImportApiError,
  type ImportResult,
  uploadXlsx,
} from '../api/imports'
import { getAccessToken } from '../auth/tokenStorage'
import { useAuth } from '../auth/useAuth'

const MAX_UPLOAD_SIZE_BYTES =
  10 * 1024 * 1024

function validateFile(
  file: File,
): string | null {
  if (
    !file.name
      .toLowerCase()
      .endsWith('.xlsx')
  ) {
    return (
      'Bitte wähle eine Datei mit der ' +
      'Endung .xlsx aus.'
    )
  }

  if (file.size === 0) {
    return 'Die ausgewählte Datei ist leer.'
  }

  if (file.size > MAX_UPLOAD_SIZE_BYTES) {
    return (
      'Die XLSX-Datei ist zu groß. ' +
      'Maximal erlaubt sind 10 MB.'
    )
  }

  return null
}

function formatFileSize(
  sizeBytes: number,
): string {
  const sizeMegabytes =
    sizeBytes / 1024 / 1024

  return (
    sizeMegabytes
      .toFixed(2)
      .replace('.', ',') + ' MB'
  )
}

function AdminImportPage() {
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
      validateFile(file)

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
        'Bitte wähle zuerst eine XLSX-Datei aus.',
      )
      return
    }

    const validationError =
      validateFile(selectedFile)

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
      const result = await uploadXlsx(
        accessToken,
        selectedFile,
      )

      setImportResult(result)
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
          : (
              'Die XLSX-Datei konnte nicht ' +
              'importiert werden.'
            ),
      )
    } finally {
      setIsUploading(false)
    }
  }

  return (
    <div className="page admin-page">
      <header className="page-header">
        <div>
          <p className="eyebrow">
            Administration
          </p>

          <h1>XLSX-Import</h1>

          <p className="muted">
            Lade einen Hager-Export hoch, um
            Ladevorgänge zu importieren und
            automatisch zu bepreisen.
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
        onSubmit={handleSubmit}
      >
        <div>
          <h2>Importdatei</h2>

          <p className="muted">
            Unterstützt werden ausschließlich
            XLSX-Dateien bis maximal 10 MB.
          </p>
        </div>

        <label className="form-field">
          <span>XLSX-Datei auswählen</span>

          <input
            type="file"
            accept={
              '.xlsx,' +
              'application/vnd.openxmlformats-' +
              'officedocument.spreadsheetml.sheet'
            }
            disabled={isUploading}
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
              isUploading ||
              selectedFile === null
            }
          >
            {isUploading
              ? 'Datei wird importiert …'
              : 'XLSX-Datei importieren'}
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
              Import abgeschlossen
            </p>

            <h2>Importergebnis</h2>
          </div>

          <dl className="import-result-grid">
            <div>
              <dt>Gelesen</dt>
              <dd>{importResult.read}</dd>
            </div>

            <div>
              <dt>Neu importiert</dt>
              <dd>{importResult.imported}</dd>
            </div>

            <div>
              <dt>Übersprungen</dt>
              <dd>{importResult.skipped}</dd>
            </div>

            <div>
              <dt>Bepreist</dt>
              <dd>{importResult.priced}</dd>
            </div>

            <div>
              <dt>Ohne Preis</dt>
              <dd>
                {importResult.missing_price}
              </dd>
            </div>

            <div>
              <dt>Ungültige Energie</dt>
              <dd>
                {importResult.invalid_energy}
              </dd>
            </div>

            <div>
              <dt>
                Unbekannte RFID-Sitzungen
              </dt>
              <dd>
                {
                  importResult
                    .unknown_rfid_sessions
                }
              </dd>
            </div>
          </dl>

          {importResult
            .unknown_rfid_numbers
            .length > 0 && (
            <div className="import-warning">
              <h3>
                Unbekannte RFID-Nummern
              </h3>

              <p>
                Für folgende RFID-Nummern
                konnte keine Karte zugeordnet
                werden:
              </p>

              <ul>
                {importResult
                  .unknown_rfid_numbers
                  .map((rfidNumber) => (
                    <li key={rfidNumber}>
                      {rfidNumber}
                    </li>
                  ))}
              </ul>
            </div>
          )}
        </section>
      )}
    </div>
  )
}

export default AdminImportPage
