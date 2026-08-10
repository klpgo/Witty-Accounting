import {
  useEffect,
  useMemo,
  useState,
} from 'react'
import {
  Link,
  useNavigate,
} from 'react-router-dom'

import {
  ChargingSessionApiError,
  listChargingSessions,
  type ChargingSession,
} from '../api/chargingSessions'
import { getAccessToken } from '../auth/tokenStorage'
import { useAuth } from '../auth/useAuth'


function formatDateTime(
  value: string,
): string {
  const date = new Date(value)

  if (Number.isNaN(date.getTime())) {
    return value
  }

  return new Intl.DateTimeFormat('de-DE', {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(date)
}


function formatNumber(
  value: string | number,
  maximumFractionDigits = 3,
): string {
  const numericValue = Number(value)

  if (!Number.isFinite(numericValue)) {
    return '–'
  }

  return new Intl.NumberFormat('de-DE', {
    minimumFractionDigits: 0,
    maximumFractionDigits,
  }).format(numericValue)
}


function formatNetCost(
  chargingSession: ChargingSession,
): string {
  const gridCost = Number(
    chargingSession.cost_grid_net ?? 0,
  )
  const pvCost = Number(
    chargingSession.cost_pv_net ?? 0,
  )

  if (
    chargingSession.cost_grid_net === null ||
    chargingSession.cost_pv_net === null ||
    !Number.isFinite(gridCost) ||
    !Number.isFinite(pvCost)
  ) {
    return '–'
  }

  return new Intl.NumberFormat('de-DE', {
    style: 'currency',
    currency: 'EUR',
  }).format(gridCost + pvCost)
}


function getStatusLabel(
  chargingSession: ChargingSession,
): string {
  if (
    chargingSession.invoice_status ===
    'finalized'
  ) {
    return 'Abgerechnet'
  }

  if (
    chargingSession.invoice_status === 'draft'
  ) {
    return 'Rechnungsentwurf'
  }

  return 'Offen'
}


function getStatusClassName(
  chargingSession: ChargingSession,
): string {
  return chargingSession.invoice_status ===
    'finalized'
    ? 'status-badge status-finalized'
    : 'status-badge status-draft'
}


function ChargingSessionsPage() {
  const navigate = useNavigate()
  const { user, signOut } = useAuth()
  const isAdmin = user?.is_admin === true

  const [
    showInvoicedSessions,
    setShowInvoicedSessions,
  ] = useState(true)

  const [
    showUninvoicedSessions,
    setShowUninvoicedSessions,
  ] = useState(true)

  const [
    chargingSessions,
    setChargingSessions,
  ] = useState<ChargingSession[]>([])

  const visibleChargingSessions = useMemo(
    () =>
      chargingSessions.filter(
        (chargingSession) =>
          chargingSession.invoiced
            ? showInvoicedSessions
            : showUninvoicedSessions,
      ),
    [
      chargingSessions,
      showInvoicedSessions,
      showUninvoicedSessions,
    ],
  )

  const [isLoading, setIsLoading] =
    useState(true)

  const [
    errorMessage,
    setErrorMessage,
  ] = useState<string | null>(null)

  useEffect(() => {
    const accessToken = getAccessToken()

    if (accessToken === null) {
      signOut()

      navigate('/login', {
        replace: true,
      })

      return
    }

    const token = accessToken
    const controller = new AbortController()

    async function loadChargingSessions():
      Promise<void> {
      try {
        const loadedChargingSessions =
          await listChargingSessions(
            token,
            controller.signal,
          )

        setChargingSessions(
          loadedChargingSessions,
        )
      } catch (error) {
        if (
          error instanceof Error &&
          error.name === 'AbortError'
        ) {
          return
        }

        if (
          error instanceof
            ChargingSessionApiError &&
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
            : 'Die Ladevorgänge konnten nicht geladen werden.',
        )
      } finally {
        if (!controller.signal.aborted) {
          setIsLoading(false)
        }
      }
    }

    void loadChargingSessions()

    return () => {
      controller.abort()
    }
  }, [navigate, signOut])

  return (
    <div className="page charging-sessions-page">
      <header className="page-header">
        <div>
          <p className="eyebrow">
            Ladehistorie
          </p>

          <h1>Ladevorgänge</h1>

          <p className="muted">
            {isAdmin
              ? 'Alle importierten Ladevorgänge, neueste zuerst.'
              : 'Ihre Ladevorgänge und deren Abrechnungsstatus.'}
          </p>
        </div>
      </header>

      {isLoading && (
        <section className="card">
          <p className="muted">
            Ladevorgänge werden geladen …
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

      {!isLoading &&
        !errorMessage &&
        chargingSessions.length === 0 && (
          <section className="card">
            <h2>
              Keine Ladevorgänge vorhanden
            </h2>

            <p className="muted">
              {isAdmin
                ? 'Es wurden noch keine Ladevorgänge importiert.'
                : 'Ihnen sind noch keine Ladevorgänge zugeordnet.'}
            </p>
          </section>
        )}

      {!isLoading &&
        !errorMessage &&
        chargingSessions.length > 0 && (
          <section className="card">
            <div className="checkbox-group">
              <label className="checkbox-field">
                <input
                  type="checkbox"
                  checked={showInvoicedSessions}
                  onChange={(event) =>
                    setShowInvoicedSessions(
                      event.target.checked,
                    )
                  }
                />

                Abgerechnete Ladevorgänge anzeigen
              </label>

              <label className="checkbox-field">
                <input
                  type="checkbox"
                  checked={showUninvoicedSessions}
                  onChange={(event) =>
                    setShowUninvoicedSessions(
                      event.target.checked,
                    )
                  }
                />

                Nicht abgerechnete Ladevorgänge anzeigen
              </label>
            </div>
          </section>
        )}

      {!isLoading &&
        !errorMessage &&
        chargingSessions.length > 0 &&
        visibleChargingSessions.length === 0 && (
          <section className="card">
            <h2>Keine passenden Ladevorgänge</h2>

            <p className="muted">
              Mit den ausgewählten Filtern werden keine
              Ladevorgänge angezeigt.
            </p>
          </section>
        )}

      {!isLoading &&
        !errorMessage &&
        visibleChargingSessions.length > 0 && (
          <section className="card table-card">
            <div className="table-scroll">
              <table className="data-table compact-table charging-sessions-table">
                <thead>
                  <tr>
                    <th>Beginn</th>
                    <th>Ende</th>

                    {isAdmin && (
                      <th>Benutzer</th>
                    )}

                    <th>RFID-Karte</th>
                    <th>Ladestation</th>

                    <th className="table-number">
                      Energie
                    </th>

                    <th className="table-number">
                      PV-Anteil
                    </th>

                    <th className="table-number">
                      Kosten netto
                    </th>

                    <th>Status</th>
                    <th>Rechnung</th>
                  </tr>
                </thead>

                <tbody>
                  {visibleChargingSessions.map(
                    (chargingSession) => (
                      <tr
                        key={chargingSession.id}
                      >
                        <td>
                          {formatDateTime(
                            chargingSession.start_time,
                          )}
                        </td>

                        <td>
                          {formatDateTime(
                            chargingSession.end_time,
                          )}
                        </td>

                        {isAdmin && (
                          <td>
                            {chargingSession.user_name ?? '-'}
                          </td>
                        )}

                        <td>
                          {chargingSession.rfid_number ?? '–'}
                        </td>

                        <td>
                          {
                            chargingSession.station_id
                          }
                        </td>

                        <td className="table-number">
                          {formatNumber(
                            chargingSession.energy_total_kwh,
                          )}{' '}
                          kWh
                        </td>

                        <td className="table-number">
                          {formatNumber(
                            chargingSession.energy_pv_kwh,
                          )}{' '}
                          kWh
                        </td>

                        <td className="table-number">
                          {formatNetCost(
                            chargingSession,
                          )}
                        </td>

                        <td>
                          <span
                            className={getStatusClassName(
                              chargingSession,
                            )}
                          >
                            {getStatusLabel(
                              chargingSession,
                            )}
                          </span>
                        </td>

                        <td>
                          {chargingSession.invoice_id !==
                          null ? (
                            <Link
                              className="table-link"
                              to={`/invoices/${chargingSession.invoice_id}`}
                            >
                              {chargingSession.invoice_number ??
                                `Entwurf #${chargingSession.invoice_id}`}
                            </Link>
                          ) : (
                            '–'
                          )}
                        </td>
                      </tr>
                    ),
                  )}
                </tbody>
              </table>
            </div>
          </section>
        )}
    </div>
  )
}

export default ChargingSessionsPage
