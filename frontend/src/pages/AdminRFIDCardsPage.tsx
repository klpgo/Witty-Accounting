import {
  type FormEvent,
  useCallback,
  useEffect,
  useMemo,
  useState,
} from 'react'
import { useNavigate } from 'react-router-dom'

import {
  createRFIDCard,
  createRFIDCardAssignment,
  listRFIDCardAssignments,
  listRFIDCards,
  RFIDCardApiError,
  updateRFIDCard,
  updateRFIDCardAssignment,
  type RFIDCard,
  type RFIDCardAssignment,
} from '../api/rfidCards'
import {
  listUsers,
  UserApiError,
  type User,
} from '../api/users'
import { getAccessToken } from '../auth/tokenStorage'
import { useAuth } from '../auth/useAuth'

function sortCards(cards: RFIDCard[]): RFIDCard[] {
  return [...cards].sort((first, second) =>
    first.rfid_number.localeCompare(
      second.rfid_number,
      'de',
    ),
  )
}

function sortAssignments(
  assignments: RFIDCardAssignment[],
): RFIDCardAssignment[] {
  return [...assignments].sort((first, second) =>
    first.valid_from.localeCompare(
      second.valid_from,
    ),
  )
}

function sortUsers(users: User[]): User[] {
  return [...users].sort((first, second) =>
    `${first.last_name} ${first.first_name}`.localeCompare(
      `${second.last_name} ${second.first_name}`,
      'de',
    ),
  )
}

function formatDateTime(value: string): string {
  const date = new Date(value)

  if (Number.isNaN(date.getTime())) {
    return value
  }

  return new Intl.DateTimeFormat(
    'de-DE',
    {
      dateStyle: 'medium',
      timeStyle: 'short',
    },
  ).format(date)
}

function toDateTimeInputValue(
  value: string | null,
): string {
  if (value === null) {
    return ''
  }

  return value.slice(0, 19)
}

function currentDateTimeInputValue(): string {
  const now = new Date()
  const timezoneOffset =
    now.getTimezoneOffset() * 60_000

  return new Date(
    now.getTime() - timezoneOffset,
  )
    .toISOString()
    .slice(0, 19)
}

function AdminRFIDCardsPage() {
  const navigate = useNavigate()
  const { signOut } = useAuth()

  const [cards, setCards] = useState<RFIDCard[]>(
    [],
  )
  const [users, setUsers] = useState<User[]>([])
  const [assignments, setAssignments] = useState<
    RFIDCardAssignment[]
  >([])

  const [selectedCardId, setSelectedCardId] =
    useState<number | null>(null)
  const [editingAssignmentId, setEditingAssignmentId] =
    useState<number | null>(null)
  const [isCreatingCard, setIsCreatingCard] =
    useState(false)

  const [rfidNumber, setRfidNumber] = useState('')
  const [description, setDescription] = useState('')
  const [cardActive, setCardActive] =
    useState(true)

  const [assignmentUserId, setAssignmentUserId] =
    useState('')
  const [validFrom, setValidFrom] = useState('')
  const [validTo, setValidTo] = useState('')

  const [isLoading, setIsLoading] =
    useState(true)
  const [isLoadingAssignments, setIsLoadingAssignments] =
    useState(false)
  const [isSavingCard, setIsSavingCard] =
    useState(false)
  const [isSavingAssignment, setIsSavingAssignment] =
    useState(false)

  const [errorMessage, setErrorMessage] =
    useState<string | null>(null)
  const [successMessage, setSuccessMessage] =
    useState<string | null>(null)

  const selectedCard = useMemo(
    () =>
      cards.find(
        (card) => card.id === selectedCardId,
      ) ?? null,
    [cards, selectedCardId],
  )

  const editingAssignment = useMemo(
    () =>
      assignments.find(
        (assignment) =>
          assignment.id === editingAssignmentId,
      ) ?? null,
    [assignments, editingAssignmentId],
  )

  const usersById = useMemo(
    () =>
      new Map(
        users.map((user) => [
          user.id,
          user,
        ]),
      ),
    [users],
  )

  const handleRequestError = useCallback(
    (
      error: unknown,
      fallbackMessage: string,
    ): void => {
      if (
        (
          error instanceof RFIDCardApiError ||
          error instanceof UserApiError
        ) &&
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

  function clearMessages(): void {
    setErrorMessage(null)
    setSuccessMessage(null)
  }

  function resetAssignmentForm(): void {
    setEditingAssignmentId(null)
    setAssignmentUserId('')
    setValidFrom(currentDateTimeInputValue())
    setValidTo('')
  }

  useEffect(() => {
    const controller = new AbortController()

    async function loadPage(): Promise<void> {
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
        const [
          loadedCards,
          loadedUsers,
        ] = await Promise.all([
          listRFIDCards(
            accessToken,
            controller.signal,
          ),
          listUsers(
            accessToken,
            controller.signal,
          ),
        ])

        const sortedCards = sortCards(loadedCards)

        setCards(sortedCards)
        setUsers(sortUsers(loadedUsers))
        setSelectedCardId(
          sortedCards[0]?.id ?? null,
        )
      } catch (error) {
        if (
          error instanceof Error &&
          error.name === 'AbortError'
        ) {
          return
        }

        handleRequestError(
          error,
          'Die RFID-Verwaltung konnte nicht geladen werden.',
        )
      } finally {
        setIsLoading(false)
      }
    }

    void loadPage()

    return () => {
      controller.abort()
    }
  }, [handleRequestError, navigate, signOut])

  useEffect(() => {
    if (isCreatingCard) {
      setRfidNumber('')
      setDescription('')
      setCardActive(true)

      return
    }

    if (selectedCard === null) {
      setRfidNumber('')
      setDescription('')
      setCardActive(true)

      return
    }

    setRfidNumber(selectedCard.rfid_number)
    setDescription(selectedCard.description ?? '')
    setCardActive(selectedCard.active)
  }, [isCreatingCard, selectedCard])

  useEffect(() => {
    const controller = new AbortController()

    async function loadAssignments(): Promise<void> {
      if (
        selectedCardId === null ||
        isCreatingCard
      ) {
        setAssignments([])
        resetAssignmentForm()

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

      setIsLoadingAssignments(true)
      setErrorMessage(null)

      try {
        const loadedAssignments =
          await listRFIDCardAssignments(
            accessToken,
            selectedCardId,
            controller.signal,
          )

        setAssignments(
          sortAssignments(loadedAssignments),
        )
        resetAssignmentForm()
      } catch (error) {
        if (
          error instanceof Error &&
          error.name === 'AbortError'
        ) {
          return
        }

        handleRequestError(
          error,
          'Die Zuordnungen konnten nicht geladen werden.',
        )
      } finally {
        setIsLoadingAssignments(false)
      }
    }

    void loadAssignments()

    return () => {
      controller.abort()
    }
  }, [
    handleRequestError,
    isCreatingCard,
    navigate,
    selectedCardId,
    signOut,
  ])

  function selectCard(cardId: number): void {
    setIsCreatingCard(false)
    setSelectedCardId(cardId)
    clearMessages()
  }

  function beginCreateCard(): void {
    setSelectedCardId(null)
    setIsCreatingCard(true)
    setAssignments([])
    resetAssignmentForm()
    clearMessages()
  }

  function cancelCreateCard(): void {
    setIsCreatingCard(false)
    setSelectedCardId(cards[0]?.id ?? null)
    clearMessages()
  }

  async function handleSaveCard(
    event: FormEvent<HTMLFormElement>,
  ): Promise<void> {
    event.preventDefault()

    const accessToken = getAccessToken()

    if (accessToken === null) {
      signOut()

      navigate('/login', {
        replace: true,
      })

      return
    }

    setIsSavingCard(true)
    clearMessages()

    try {
      if (isCreatingCard) {
        const createdCard = await createRFIDCard(
          accessToken,
          {
            rfid_number: rfidNumber,
            description:
              description.trim() || null,
            active: cardActive,
          },
        )

        setCards((currentCards) =>
          sortCards([
            ...currentCards,
            createdCard,
          ]),
        )
        setIsCreatingCard(false)
        setSelectedCardId(createdCard.id)

        setSuccessMessage(
          `RFID-Karte ${createdCard.rfid_number} wurde angelegt.`,
        )
      } else if (selectedCard !== null) {
        const updatedCard = await updateRFIDCard(
          accessToken,
          selectedCard.id,
          {
            rfid_number: rfidNumber,
            description:
              description.trim() || null,
            active: cardActive,
          },
        )

        setCards((currentCards) =>
          sortCards(
            currentCards.map((card) =>
              card.id === updatedCard.id
                ? updatedCard
                : card,
            ),
          ),
        )

        setSuccessMessage(
          `RFID-Karte ${updatedCard.rfid_number} wurde gespeichert.`,
        )
      }
    } catch (error) {
      handleRequestError(
        error,
        'Die RFID-Karte konnte nicht gespeichert werden.',
      )
    } finally {
      setIsSavingCard(false)
    }
  }

  function beginCreateAssignment(): void {
    resetAssignmentForm()
    clearMessages()
  }

  function beginEditAssignment(
    assignment: RFIDCardAssignment,
  ): void {
    setEditingAssignmentId(assignment.id)
    setAssignmentUserId(
      String(assignment.user_id),
    )
    setValidFrom(
      toDateTimeInputValue(
        assignment.valid_from,
      ),
    )
    setValidTo(
      toDateTimeInputValue(
        assignment.valid_to,
      ),
    )
    clearMessages()
  }

  async function handleSaveAssignment(
    event: FormEvent<HTMLFormElement>,
  ): Promise<void> {
    event.preventDefault()

    if (selectedCard === null) {
      return
    }

    const userId = Number(assignmentUserId)

    if (!Number.isInteger(userId) || userId <= 0) {
      setErrorMessage(
        'Bitte einen Benutzer auswählen.',
      )

      return
    }

    if (!validFrom) {
      setErrorMessage(
        'Bitte den Beginn der Zuordnung angeben.',
      )

      return
    }

    if (
      validTo &&
      new Date(validTo).getTime() <=
        new Date(validFrom).getTime()
    ) {
      setErrorMessage(
        'Das Ende der Zuordnung muss nach ihrem Beginn liegen.',
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

    setIsSavingAssignment(true)
    clearMessages()

    try {
      let savedAssignment: RFIDCardAssignment

      if (editingAssignment !== null) {
        savedAssignment =
          await updateRFIDCardAssignment(
            accessToken,
            editingAssignment.id,
            {
              user_id: userId,
              valid_from: validFrom,
              valid_to: validTo || null,
            },
          )

        setAssignments((currentAssignments) =>
          sortAssignments(
            currentAssignments.map(
              (assignment) =>
                assignment.id ===
                savedAssignment.id
                  ? savedAssignment
                  : assignment,
            ),
          ),
        )

        setSuccessMessage(
          'Die RFID-Zuordnung wurde gespeichert.',
        )
      } else {
        savedAssignment =
          await createRFIDCardAssignment(
            accessToken,
            selectedCard.id,
            {
              user_id: userId,
              valid_from: validFrom,
              valid_to: validTo || null,
            },
          )

        setAssignments((currentAssignments) =>
          sortAssignments([
            ...currentAssignments,
            savedAssignment,
          ]),
        )

        setSuccessMessage(
          'Die RFID-Zuordnung wurde angelegt.',
        )
      }

      resetAssignmentForm()
    } catch (error) {
      handleRequestError(
        error,
        'Die RFID-Zuordnung konnte nicht gespeichert werden.',
      )
    } finally {
      setIsSavingAssignment(false)
    }
  }

  return (
    <div className="page admin-page">
      <header className="page-header">
        <div>
          <p className="eyebrow">
            Administration
          </p>

          <h1>RFID-Karten</h1>

          <p className="muted">
            Karten verwalten und zeitlich gültigen
            Benutzern zuordnen.
          </p>
        </div>

        <button
          className="button button-primary"
          type="button"
          onClick={beginCreateCard}
        >
          Neue RFID-Karte
        </button>
      </header>

      {isLoading && (
        <section className="card">
          <p className="muted">
            RFID-Karten werden geladen …
          </p>
        </section>
      )}

      {!isLoading && errorMessage && (
        <section
          className="card form-error admin-message"
          role="alert"
        >
          {errorMessage}
        </section>
      )}

      {!isLoading && successMessage && (
        <section
          className="card form-success admin-message"
          role="status"
        >
          {successMessage}
        </section>
      )}

      {!isLoading && (
        <div className="admin-layout">
          <section className="card table-card">
            {cards.length === 0 ? (
              <div className="empty-card-content">
                <h2>Keine RFID-Karten</h2>

                <p className="muted">
                  Legen Sie die erste RFID-Karte an.
                </p>
              </div>
            ) : (
              <div className="table-scroll">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>RFID-Nummer</th>
                      <th>Beschreibung</th>
                      <th>Status</th>
                      <th />
                    </tr>
                  </thead>

                  <tbody>
                    {cards.map((card) => (
                      <tr
                        key={card.id}
                        className={
                          card.id === selectedCardId &&
                          !isCreatingCard
                            ? 'data-table-row-selected'
                            : undefined
                        }
                      >
                        <td>
                          <strong>
                            {card.rfid_number}
                          </strong>
                        </td>

                        <td>
                          {card.description ?? '–'}
                        </td>

                        <td>
                          <span
                            className={
                              card.active
                                ? 'status-badge status-active'
                                : 'status-badge status-inactive'
                            }
                          >
                            {card.active
                              ? 'Aktiv'
                              : 'Inaktiv'}
                          </span>
                        </td>

                        <td>
                          <button
                            className="button button-secondary"
                            type="button"
                            onClick={() =>
                              selectCard(card.id)
                            }
                          >
                            Bearbeiten
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>

          <div className="admin-editor-stack">
            <section className="card admin-editor">
              <div>
                <p className="eyebrow">
                  {isCreatingCard
                    ? 'Neue Karte'
                    : selectedCard === null
                      ? 'Keine Karte ausgewählt'
                      : `RFID-Karte #${selectedCard.id}`}
                </p>

                <h2>
                  {isCreatingCard
                    ? 'RFID-Karte anlegen'
                    : selectedCard?.rfid_number ??
                      'RFID-Karte'}
                </h2>
              </div>

              {(isCreatingCard ||
                selectedCard !== null) && (
                <form
                  className="admin-form"
                  onSubmit={handleSaveCard}
                >
                  <label className="form-field">
                    RFID-Nummer
                    <input
                      type="text"
                      value={rfidNumber}
                      required
                      maxLength={100}
                      onChange={(event) =>
                        setRfidNumber(
                          event.target.value,
                        )
                      }
                    />
                  </label>

                  <label className="form-field">
                    Beschreibung
                    <input
                      type="text"
                      value={description}
                      maxLength={255}
                      onChange={(event) =>
                        setDescription(
                          event.target.value,
                        )
                      }
                    />
                  </label>

                  <label className="checkbox-field">
                    <input
                      type="checkbox"
                      checked={cardActive}
                      onChange={(event) =>
                        setCardActive(
                          event.target.checked,
                        )
                      }
                    />

                    RFID-Karte ist aktiv
                  </label>

                  <p className="form-hint">
                    Karten werden nicht gelöscht.
                    Nicht mehr verwendete Karten
                    können deaktiviert werden.
                  </p>

                  <div className="form-actions">
                    {isCreatingCard && (
                      <button
                        className="button button-secondary"
                        type="button"
                        onClick={cancelCreateCard}
                      >
                        Abbrechen
                      </button>
                    )}

                    <button
                      className="button button-primary"
                      type="submit"
                      disabled={isSavingCard}
                    >
                      {isSavingCard
                        ? 'Wird gespeichert …'
                        : isCreatingCard
                          ? 'Karte anlegen'
                          : 'Karte speichern'}
                    </button>
                  </div>
                </form>
              )}
            </section>

            {!isCreatingCard &&
              selectedCard !== null && (
                <section className="card admin-editor">
                  <div className="admin-section-header">
                    <div>
                      <p className="eyebrow">
                        Historie
                      </p>

                      <h2>Benutzerzuordnungen</h2>
                    </div>

                    <button
                      className="button button-secondary"
                      type="button"
                      onClick={beginCreateAssignment}
                    >
                      Neue Zuordnung
                    </button>
                  </div>

                  {isLoadingAssignments && (
                    <p className="muted">
                      Zuordnungen werden geladen …
                    </p>
                  )}

                  {!isLoadingAssignments &&
                    assignments.length === 0 && (
                      <p className="muted">
                        Für diese Karte gibt es noch
                        keine Benutzerzuordnung.
                      </p>
                    )}

                  {!isLoadingAssignments &&
                    assignments.length > 0 && (
                      <div className="table-scroll">
                        <table className="data-table compact-table">
                          <thead>
                            <tr>
                              <th>Benutzer</th>
                              <th>Von</th>
                              <th>Bis</th>
                              <th />
                            </tr>
                          </thead>

                          <tbody>
                            {assignments.map(
                              (assignment) => {
                                const assignedUser =
                                  usersById.get(
                                    assignment.user_id,
                                  )

                                return (
                                  <tr
                                    key={assignment.id}
                                    className={
                                      assignment.id ===
                                      editingAssignmentId
                                        ? 'data-table-row-selected'
                                        : undefined
                                    }
                                  >
                                    <td>
                                      {assignedUser
                                        ? `${assignedUser.first_name} ${assignedUser.last_name}`
                                        : `Benutzer #${assignment.user_id}`}
                                    </td>

                                    <td>
                                      {formatDateTime(
                                        assignment.valid_from,
                                      )}
                                    </td>

                                    <td>
                                      {assignment.valid_to
                                        ? formatDateTime(
                                            assignment.valid_to,
                                          )
                                        : 'Offen'}
                                    </td>

                                    <td>
                                      <button
                                        className="button button-secondary"
                                        type="button"
                                        onClick={() =>
                                          beginEditAssignment(
                                            assignment,
                                          )
                                        }
                                      >
                                        Bearbeiten
                                      </button>
                                    </td>
                                  </tr>
                                )
                              },
                            )}
                          </tbody>
                        </table>
                      </div>
                    )}

                  <div className="admin-divider" />

                  <div>
                    <h2>
                      {editingAssignment === null
                        ? 'Neue Zuordnung'
                        : `Zuordnung #${editingAssignment.id} bearbeiten`}
                    </h2>

                    <p className="muted">
                      Bereits verwendete Zuordnungen
                      sind zum Schutz der
                      Abrechnungshistorie nur
                      eingeschränkt änderbar.
                    </p>
                  </div>

                  <form
                    className="admin-form"
                    onSubmit={handleSaveAssignment}
                  >
                    <label className="form-field">
                      Benutzer
                      <select
                        value={assignmentUserId}
                        required
                        onChange={(event) =>
                          setAssignmentUserId(
                            event.target.value,
                          )
                        }
                      >
                        <option value="">
                          Bitte auswählen
                        </option>

                        {users.map((user) => (
                          <option
                            key={user.id}
                            value={user.id}
                          >
                            {user.first_name}{' '}
                            {user.last_name}
                            {!user.active
                              ? ' (inaktiv)'
                              : ''}
                          </option>
                        ))}
                      </select>
                    </label>

                    <div className="form-grid">
                      <label className="form-field">
                        Gültig von
                        <input
                          type="datetime-local"
                          step="1"
                          value={validFrom}
                          required
                          onChange={(event) =>
                            setValidFrom(
                              event.target.value,
                            )
                          }
                        />
                      </label>

                      <label className="form-field">
                        Gültig bis
                        <input
                          type="datetime-local"
                          step="1"
                          value={validTo}
                          onChange={(event) =>
                            setValidTo(
                              event.target.value,
                            )
                          }
                        />
                      </label>
                    </div>

                    <p className="form-hint">
                      Ein leeres Enddatum bedeutet,
                      dass die Zuordnung zeitlich
                      offen bleibt.
                    </p>

                    <div className="form-actions">
                      {editingAssignment !== null && (
                        <button
                          className="button button-secondary"
                          type="button"
                          onClick={
                            beginCreateAssignment
                          }
                        >
                          Abbrechen
                        </button>
                      )}

                      <button
                        className="button button-primary"
                        type="submit"
                        disabled={
                          isSavingAssignment
                        }
                      >
                        {isSavingAssignment
                          ? 'Wird gespeichert …'
                          : editingAssignment === null
                            ? 'Zuordnung anlegen'
                            : 'Zuordnung speichern'}
                      </button>
                    </div>
                  </form>
                </section>
              )}
          </div>
        </div>
      )}
    </div>
  )
}

export default AdminRFIDCardsPage
