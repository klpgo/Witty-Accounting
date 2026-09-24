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

const MAX_UPLOAD_SIZE_BYTES =
  10 * 1024 * 1024

function validateFile(
  file: File,
): string | null {
  if (getImportFileType(file.name) === null) {
    return (
      'Bitte wähle eine Datei mit der ' +
      'Endung .xlsx oder .json aus.'
    )
  }

  if (file.size === 0) {
    return 'Die ausgewählte Datei ist leer.'
  }

  if (file.size > MAX_UPLOAD_SIZE_BYTES) {
    return (
      'Die Datei ist zu groß. ' +
      'Maximal erlaubt sind 10 MB.'
    )
  }

  return null
}

function formatIsoDate(value: string): string {
  const [year, month, day] = value.split('-')

  return `${day}.${month}.${year}`
}


interface RfidIssueGroup {
  title: string
  hint: string
  numbers: string[]
}

function rfidIssueGroups(
  result: ImportResult,
): RfidIssueGroup[] {
  const hasDetails =
    result.unknown_rfid_cards !== undefined ||
    result.inactive_rfid_cards !== undefined ||
    result.unassigned_rfid_numbers !== undefined

  if (!hasDetails) {
    return [
      {
        title: 'Ohne Zuordnung',
        hint: 'Für diese RFID-Nummern gab es keine gültige Kartenzuordnung.',
        numbers: result.unknown_rfid_numbers,
      },
    ]
  }

  const groups: RfidIssueGroup[] = [
    {
      title: 'Keine Benutzerzuordnung zum Ladezeitpunkt',
      hint:
        'Die Karte existiert, aber zum Zeitpunkt des Ladevorgangs ' +
        'war keine Benutzerzuordnung gültig. Zuordnung mit ' +
        'passendem „Gültig von“ anlegen.',
      numbers: result.unassigned_rfid_numbers ?? [],
    },
    {
      title: 'Karte deaktiviert',
      hint:
        'Die Karte existiert, ist aber deaktiviert. ' +
        'Karte aktivieren, falls die Ladevorgänge abgerechnet werden sollen.',
      numbers: result.inactive_rfid_cards ?? [],
    },
    {
      title: 'Karte nicht angelegt',
      hint:
        'Diese RFID-Nummern sind in Witty unbekannt. ' +
        'Karte anlegen und einem Benutzer zuordnen.',
      numbers: result.unknown_rfid_cards ?? [],
    },
  ]

  return groups.filter((group) => group.numbers.length > 0)
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
        'Bitte wähle zuerst eine Importdatei aus.',
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
          : (
              'Die Datei konnte nicht ' +
              'importiert werden.'
            ),
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
        'Das Startdatum liegt nach dem Enddatum.',
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
          : (
              'Die Ladevorgänge konnten nicht ' +
              'aus Hager flow abgerufen werden.'
            ),
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
            Administration
          </p>

          <h1>Import</h1>

          <p className="muted">
            Ladevorgänge direkt aus Hager flow
            abrufen oder aus einer Datei (XLSX-Export
            bzw. JSON aus hager-fetch) importieren.
            Neue Ladevorgänge werden automatisch
            bepreist, bereits vorhandene
            übersprungen.
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
          <h2>Abruf aus Hager flow</h2>

          <p className="muted">
            Ruft die Ladevorgänge direkt mit den
            hinterlegten Zugangsdaten ab. Ohne
            Zeitraum ab dem letzten erfolgreichen
            Abruf (mit 3 Tagen Überlappung,
            frühestens ab Abrechnungsbeginn);
            bereits vorhandene Ladevorgänge werden
            übersprungen.
          </p>
        </div>

        <div className="form-grid">
          <label className="form-field">
            <span>Von (optional)</span>
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
            <span>Bis (optional)</span>
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
          Alle Ladevorgänge abrufen (vollständiger
          Abgleich, dauert länger)
        </label>

        <div className="form-actions">
          <button
            className="button button-primary"
            type="submit"
            disabled={isBusy}
          >
            {isFetchingHager
              ? 'Ladevorgänge werden abgerufen …'
              : 'Jetzt aus Hager flow abrufen'}
          </button>
        </div>
      </form>

      <form
        className="card import-form"
        onSubmit={handleSubmit}
      >
        <div>
          <h2>Import aus Datei</h2>

          <p className="muted">
            Unterstützt werden XLSX- und
            JSON-Dateien bis maximal 10 MB.
          </p>
        </div>

        <label className="form-field">
          <span>Datei auswählen</span>

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
              ? 'Datei wird importiert …'
              : 'Datei importieren'}
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
                Ohne Kartenzuordnung
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
                ? `Aus Hager flow abgerufen ab ${formatIsoDate(
                    importResult.fetched_from,
                  )}.`
                : 'Alle Ladevorgänge aus Hager flow abgerufen.'}
            </p>
          )}

          {(importResult.reassigned_sessions ?? 0) > 0 && (
            <p className="form-success" role="status">
              {importResult.reassigned_sessions} ältere
              {' '}
              {importResult.reassigned_sessions === 1
                ? 'Ladevorgang wurde'
                : 'Ladevorgänge wurden'}
              {' '}
              nachträglich einer Kartenzuordnung
              zugeordnet.
            </p>
          )}

          {importResult
            .unknown_rfid_numbers
            .length > 0 && (
            <div className="import-warning">
              <h3>
                Nicht zugeordnete RFID-Karten
              </h3>

              <p>
                {importResult.unknown_rfid_sessions}
                {' '}
                {importResult.unknown_rfid_sessions === 1
                  ? 'Ladevorgang konnte'
                  : 'Ladevorgänge konnten'}
                {' '}
                keinem Benutzer zugeordnet werden.
                Die RFID-Nummern sind gespeichert:
                Sobald die Ursache behoben ist, werden
                nicht abgerechnete Ladevorgänge
                automatisch nachträglich zugeordnet.
              </p>

              {rfidIssueGroups(importResult).map(
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
