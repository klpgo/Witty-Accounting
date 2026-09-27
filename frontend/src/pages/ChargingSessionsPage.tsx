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
  discardChargingSessions,
  listChargingSessions,
  restoreChargingSessions,
  type ChargingSession,
} from '../api/chargingSessions'
import { getAccessToken } from '../auth/tokenStorage'
import { useAuth } from '../auth/useAuth'


const DATE_FORMAT = new Intl.DateTimeFormat('de-DE', {
  day: '2-digit',
  month: '2-digit',
  year: 'numeric',
})

const TIME_FORMAT = new Intl.DateTimeFormat('de-DE', {
  hour: '2-digit',
  minute: '2-digit',
})

const SHORT_DATE_TIME_FORMAT = new Intl.DateTimeFormat('de-DE', {
  day: '2-digit',
  month: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
})


// Zeitraum in zwei Zeilen: Datum, darunter die Uhrzeiten.
// Endet der Vorgang an einem anderen Tag, steht beim Ende das Datum mit.
function formatPeriod(
  start: string,
  end: string,
): { date: string; times: string } {
  const startDate = new Date(start)
  const endDate = new Date(end)

  if (
    Number.isNaN(startDate.getTime()) ||
    Number.isNaN(endDate.getTime())
  ) {
    return { date: start, times: end }
  }

  const sameDay =
    startDate.toDateString() === endDate.toDateString()

  return {
    date: DATE_FORMAT.format(startDate),
    times:
      `${TIME_FORMAT.format(startDate)} – ` +
      (sameDay
        ? TIME_FORMAT.format(endDate)
        : SHORT_DATE_TIME_FORMAT.format(endDate)),
  }
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


function isDiscardable(
  chargingSession: ChargingSession,
): boolean {
  return (
    !chargingSession.discarded &&
    !chargingSession.invoiced &&
    chargingSession.invoice_id === null
  )
}


function getStatusLabel(
  chargingSession: ChargingSession,
): string {
  if (chargingSession.discarded) {
    return 'Verworfen'
  }

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
  if (chargingSession.discarded) {
    return 'status-badge status-discarded'
  }

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

  const [selectedIds, setSelectedIds] =
    useState<Set<number>>(new Set())
  const [discardReason, setDiscardReason] =
    useState('')
  const [isChanging, setIsChanging] =
    useState(false)
  const [actionMessage, setActionMessage] =
    useState<string | null>(null)
  const [actionError, setActionError] =
    useState<string | null>(null)
  const [reloadKey, setReloadKey] = useState(0)

  const [showDiscarded, setShowDiscarded] =
    useState(false)

  const visibleChargingSessions = useMemo(
    () =>
      chargingSessions.filter((chargingSession) => {
        if (chargingSession.discarded) {
          return showDiscarded
        }

        return chargingSession.invoiced
          ? showInvoicedSessions
          : showUninvoicedSessions
      }),
    [
      chargingSessions,
      showDiscarded,
      showInvoicedSessions,
      showUninvoicedSessions,
    ],
  )

  // Kennzahlen über alle geladenen Vorgänge (unabhängig von den Filtern)
  const statistics = useMemo(() => {
    let invoiced = 0
    let open = 0
    let discarded = 0

    for (const chargingSession of chargingSessions) {
      if (chargingSession.discarded) {
        discarded += 1
      } else if (chargingSession.invoiced) {
        invoiced += 1
      } else {
        open += 1
      }
    }

    return {
      total: chargingSessions.length,
      invoiced,
      open,
      discarded,
    }
  }, [chargingSessions])

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
            isAdmin,
          )

        setChargingSessions(
          loadedChargingSessions,
        )
        setSelectedIds(new Set())
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
  }, [navigate, signOut, isAdmin, reloadKey])

  const selectableIds = visibleChargingSessions
    .filter(isDiscardable)
    .map((chargingSession) => chargingSession.id)

  const allSelected =
    selectableIds.length > 0 &&
    selectableIds.every((id) => selectedIds.has(id))

  function toggleSelected(id: number): void {
    setSelectedIds((current) => {
      const next = new Set(current)

      if (next.has(id)) {
        next.delete(id)
      } else {
        next.add(id)
      }

      return next
    })
  }

  function toggleAll(): void {
    setSelectedIds(
      allSelected ? new Set() : new Set(selectableIds),
    )
  }

  async function runAction(
    action: () => Promise<number>,
    successText: (changed: number) => string,
  ): Promise<void> {
    const accessToken = getAccessToken()

    if (accessToken === null) {
      signOut()
      navigate('/login', { replace: true })
      return
    }

    setIsChanging(true)
    setActionMessage(null)
    setActionError(null)

    try {
      const changed = await action()
      setActionMessage(successText(changed))
      setDiscardReason('')
      setReloadKey((key) => key + 1)
    } catch (error) {
      if (
        error instanceof ChargingSessionApiError &&
        error.status === 401
      ) {
        signOut()
        navigate('/login', { replace: true })
        return
      }

      setActionError(
        error instanceof Error
          ? error.message
          : 'Die Aktion ist fehlgeschlagen.',
      )
    } finally {
      setIsChanging(false)
    }
  }

  function handleDiscard(): void {
    const ids = [...selectedIds]

    if (
      ids.length === 0 ||
      !window.confirm(
        `${ids.length} Ladevorgang/Ladevorgänge verwerfen? ` +
          'Sie werden nicht mehr angezeigt, bepreist oder abgerechnet ' +
          'und lassen sich über „Verworfene anzeigen“ wiederherstellen.',
      )
    ) {
      return
    }

    const token = getAccessToken() ?? ''

    void runAction(
      () =>
        discardChargingSessions(
          token,
          ids,
          discardReason.trim() || undefined,
        ),
      (changed) =>
        `${changed} Ladevorgang/Ladevorgänge verworfen.`,
    )
  }

  function handleRestore(id: number): void {
    const token = getAccessToken() ?? ''

    void runAction(
      () => restoreChargingSessions(token, [id]),
      () => 'Ladevorgang wiederhergestellt.',
    )
  }

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
          <section className="card sessions-overview">
            <dl className="sessions-statistics">
              <div>
                <dt>Ladevorgänge geladen</dt>
                <dd>{statistics.total}</dd>
              </div>
              <div>
                <dt>abgerechnet</dt>
                <dd>{statistics.invoiced}</dd>
              </div>
              <div>
                <dt>nicht abgerechnet</dt>
                <dd>{statistics.open}</dd>
              </div>
              {isAdmin && (
                <div>
                  <dt>verworfen</dt>
                  <dd>{statistics.discarded}</dd>
                </div>
              )}
            </dl>

            <div className="checkbox-group sessions-filters">
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

              {isAdmin && (
                <label className="checkbox-field">
                  <input
                    type="checkbox"
                    checked={showDiscarded}
                    onChange={(event) => {
                      setShowDiscarded(event.target.checked)
                    }}
                  />

                  Verworfene Ladevorgänge anzeigen
                </label>
              )}
            </div>
          </section>
        )}

      {isAdmin && (actionMessage || actionError) && (
        <section
          className={
            actionError
              ? 'card form-error'
              : 'card form-success'
          }
          role={actionError ? 'alert' : 'status'}
        >
          {actionError ?? actionMessage}
        </section>
      )}

      {isAdmin && selectedIds.size > 0 && (
        <section className="card session-bulk-actions">
          <strong>
            {selectedIds.size} ausgewählt
          </strong>

          <input
            type="text"
            value={discardReason}
            maxLength={255}
            placeholder="Grund (optional), z. B. Testladung"
            disabled={isChanging}
            onChange={(event) => {
              setDiscardReason(event.target.value)
            }}
          />

          <button
            className="button button-danger"
            type="button"
            disabled={isChanging}
            onClick={handleDiscard}
          >
            {isChanging ? 'Wird verworfen …' : 'Auswahl verwerfen'}
          </button>

          <button
            className="button button-secondary"
            type="button"
            disabled={isChanging}
            onClick={() => {
              setSelectedIds(new Set())
            }}
          >
            Auswahl aufheben
          </button>
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
                    {isAdmin && (
                      <th className="session-select">
                        <input
                          type="checkbox"
                          aria-label="Alle verwerfbaren auswählen"
                          checked={allSelected}
                          disabled={selectableIds.length === 0}
                          onChange={toggleAll}
                        />
                      </th>
                    )}
                    <th>Zeitraum</th>

                    {isAdmin && (
                      <th className="session-user">Benutzer</th>
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
                    {isAdmin && showDiscarded && <th />}
                  </tr>
                </thead>

                <tbody>
                  {visibleChargingSessions.map(
                    (chargingSession) => (
                      <tr
                        key={chargingSession.id}
                        className={
                          chargingSession.discarded
                            ? 'session-discarded'
                            : undefined
                        }
                      >
                        {isAdmin && (
                          <td className="session-select">
                            {isDiscardable(chargingSession) && (
                              <input
                                type="checkbox"
                                aria-label="Ladevorgang auswählen"
                                checked={selectedIds.has(
                                  chargingSession.id,
                                )}
                                onChange={() => {
                                  toggleSelected(chargingSession.id)
                                }}
                              />
                            )}
                          </td>
                        )}

                        <td className="session-period">
                          {(() => {
                            const period = formatPeriod(
                              chargingSession.start_time,
                              chargingSession.end_time,
                            )

                            return (
                              <>
                                <span>{period.date}</span>
                                <span className="muted">
                                  {period.times}
                                </span>
                              </>
                            )
                          })()}
                        </td>

                        {isAdmin && (
                          <td className="session-user">
                            {chargingSession.user_name ?? '–'}
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
                            title={
                              chargingSession.discard_reason ??
                              undefined
                            }
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

                        {isAdmin && showDiscarded && (
                          <td>
                            {chargingSession.discarded && (
                              <button
                                className="button button-secondary"
                                type="button"
                                disabled={isChanging}
                                onClick={() => {
                                  handleRestore(chargingSession.id)
                                }}
                              >
                                Wiederherstellen
                              </button>
                            )}
                          </td>
                        )}
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
