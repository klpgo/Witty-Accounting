import {
  type FormEvent,
  useCallback,
  useEffect,
  useMemo,
  useState,
} from 'react'
import { useNavigate } from 'react-router-dom'

import {
  createUser,
  getInvoiceDeliveryFlags,
  getInvoiceDeliveryMethod,
  listUsers,
  resetUserPassword,
  updateUser,
  UserApiError,
  type User,
  type InvoiceDeliveryMethod,
} from '../api/users'
import { getAccessToken } from '../auth/tokenStorage'
import { useAuth } from '../auth/useAuth'
import {
  getGlobalSettings,
  SettingsApiError,
} from '../api/settings'

function sortUsers(users: User[]): User[] {
  return [...users].sort((first, second) => {
    const firstName = [
      first.last_name,
      first.first_name,
      first.email,
    ].join(' ')

    const secondName = [
      second.last_name,
      second.first_name,
      second.email,
    ].join(' ')

    return firstName.localeCompare(
      secondName,
      'de',
    )
  })
}

function formatLastLogin(
  value: string | null,
): string {
  if (value === null) {
    return 'Noch nie'
  }

  const hasTimezone = /(?:Z|[+-]\d{2}:\d{2})$/i.test(
    value,
  )
  const date = new Date(
    hasTimezone ? value : `${value}Z`,
  )

  if (Number.isNaN(date.getTime())) {
    return value
  }

  return new Intl.DateTimeFormat('de-DE', {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(date)
}

function AdminUsersPage() {
  const navigate = useNavigate()
  const { user: currentUser, signOut } = useAuth()
  const [
    hideInactiveUsers,
    setHideInactiveUsers,
  ] = useState(true)

  const [users, setUsers] = useState<User[]>([])
  const [selectedUserId, setSelectedUserId] =
    useState<number | null>(null)
  const visibleUsers = useMemo(
    () =>
      hideInactiveUsers
        ? users.filter(
            (managedUser) =>
              managedUser.active,
          )
        : users,
    [hideInactiveUsers, users],
  )
  const [isCreating, setIsCreating] =
    useState(false)

  const [email, setEmail] = useState('')
  const [firstName, setFirstName] = useState('')
  const [lastName, setLastName] = useState('')
  const [address, setAddress] = useState('')
  const [invoiceDeliveryMethod, setInvoiceDeliveryMethod] =
    useState<InvoiceDeliveryMethod>('email')
  const [active, setActive] = useState(false)
  const [isAdmin, setIsAdmin] = useState(false)

  const [newPassword, setNewPassword] =
    useState('')
  const [confirmPassword, setConfirmPassword] =
    useState('')
  const [passwordMinLength, setPasswordMinLength] =
    useState(8)

  const [isLoading, setIsLoading] =
    useState(true)
  const [isSaving, setIsSaving] =
    useState(false)
  const [isResettingPassword, setIsResettingPassword] =
    useState(false)

  const [errorMessage, setErrorMessage] =
    useState<string | null>(null)
  const [successMessage, setSuccessMessage] =
    useState<string | null>(null)

  const selectedUser = useMemo(
    () =>
      users.find(
        (candidate) =>
          candidate.id === selectedUserId,
      ) ?? null,
    [selectedUserId, users],
  )

  useEffect(() => {
    if (
      isCreating ||
      !hideInactiveUsers ||
      selectedUser === null ||
      selectedUser.active
    ) {
      return
    }

    setSelectedUserId(
      users.find(
        (managedUser) =>
          managedUser.active,
      )?.id ?? null,
    )
  }, [
    hideInactiveUsers,
    isCreating,
    selectedUser,
    users,
  ])

  const isOwnAccount =
    selectedUser !== null &&
    selectedUser.id === currentUser?.id

    const handleRequestError = useCallback(
      (
        error: unknown,
        fallbackMessage: string,
      ): void => {
        if (
          (
            error instanceof UserApiError ||
            error instanceof SettingsApiError
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

  useEffect(() => {
    const controller = new AbortController()

    async function loadUsers(): Promise<void> {
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
        const [userResults, loadedSettings] =
          await Promise.all([
            listUsers(
              accessToken,
              controller.signal,
            ),
            getGlobalSettings(
              accessToken,
              controller.signal,
            ),
          ])

        const loadedUsers = sortUsers(
          userResults,
        )

        setPasswordMinLength(
          loadedSettings.password_min_length,
        )

        setUsers(loadedUsers)

        setSelectedUserId((currentId) => {
          if (
            currentId !== null &&
            loadedUsers.some(
              (loadedUser) =>
                loadedUser.id === currentId,
            )
          ) {
            return currentId
          }

          return loadedUsers[0]?.id ?? null
        })
      } catch (error) {
        if (
          error instanceof Error &&
          error.name === 'AbortError'
        ) {
          return
        }

        handleRequestError(
          error,
          'Die Benutzer konnten nicht geladen werden.',
        )
      } finally {
        setIsLoading(false)
      }
    }

    void loadUsers()

    return () => {
      controller.abort()
    }
  }, [handleRequestError, navigate, signOut])

  useEffect(() => {
    if (isCreating) {
      setEmail('')
      setFirstName('')
      setLastName('')
      setAddress('')
      setInvoiceDeliveryMethod('email')
      setActive(true)
      setIsAdmin(false)
      setNewPassword('')
      setConfirmPassword('')

      return
    }

    if (selectedUser === null) {
      setEmail('')
      setFirstName('')
      setLastName('')
      setAddress('')
      setInvoiceDeliveryMethod('email')
      setActive(false)
      setIsAdmin(false)
      setNewPassword('')
      setConfirmPassword('')

      return
    }

    setEmail(selectedUser.email)
    setFirstName(selectedUser.first_name)
    setLastName(selectedUser.last_name)
    setAddress(selectedUser.address ?? '')
    setInvoiceDeliveryMethod(
      getInvoiceDeliveryMethod(selectedUser),
    )
    setActive(selectedUser.active)
    setIsAdmin(selectedUser.is_admin)
    setNewPassword('')
    setConfirmPassword('')
  }, [isCreating, selectedUser])

  function selectUser(userId: number): void {
    setIsCreating(false)
    setSelectedUserId(userId)
    setErrorMessage(null)
    setSuccessMessage(null)
  }

  function startCreatingUser(): void {
    setIsCreating(true)
    setSelectedUserId(null)
    setErrorMessage(null)
    setSuccessMessage(null)
  }

  async function handleSaveUser(
    event: FormEvent<HTMLFormElement>,
  ): Promise<void> {
    event.preventDefault()

    if (!isCreating && selectedUser === null) {
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
      if (isCreating) {
        const createdUser = await createUser(
          accessToken,
          {
            email,
            first_name: firstName,
            last_name: lastName,
            address: address.trim() || null,
            ...getInvoiceDeliveryFlags(
              invoiceDeliveryMethod,
            ),
            active,
            is_admin: isAdmin,
          },
        )

        setUsers((currentUsers) =>
          sortUsers([
            ...currentUsers,
            createdUser,
          ]),
        )

        setIsCreating(false)
        setSelectedUserId(createdUser.id)

        setSuccessMessage(
          `Benutzer ${createdUser.first_name} ` +
            `${createdUser.last_name} wurde angelegt. ` +
            'Die Einladungsmail wurde versendet.',
        )

        return
      }

      if (selectedUser === null) {
        return
      }

      const updatedUser = await updateUser(
        accessToken,
        selectedUser.id,
        {
          email,
          first_name: firstName,
          last_name: lastName,
          address: address.trim() || null,
          ...getInvoiceDeliveryFlags(
            invoiceDeliveryMethod,
          ),
          active,
          is_admin: isAdmin,
        },
      )

      setUsers((currentUsers) =>
        sortUsers(
          currentUsers.map((candidate) =>
            candidate.id === updatedUser.id
              ? updatedUser
              : candidate,
          ),
        ),
      )

      setSuccessMessage(
        `Benutzer ${updatedUser.first_name} ` +
          `${updatedUser.last_name} wurde gespeichert.`,
      )
    } catch (error) {
      handleRequestError(
        error,
        isCreating
          ? 'Der Benutzer konnte nicht angelegt werden.'
          : 'Der Benutzer konnte nicht gespeichert werden.',
      )
    } finally {
      setIsSaving(false)
    }
  }

  async function handlePasswordReset(
    event: FormEvent<HTMLFormElement>,
  ): Promise<void> {
    event.preventDefault()

    if (selectedUser === null) {
      return
    }

    if (newPassword.length < passwordMinLength) {
      setErrorMessage(
        'Das neue Passwort muss mindestens ' +
          `${passwordMinLength} Zeichen lang sein.`,
      )

      return
    }

    if (newPassword !== confirmPassword) {
      setErrorMessage(
        'Die beiden Passwörter stimmen nicht überein.',
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

    setIsResettingPassword(true)
    setErrorMessage(null)
    setSuccessMessage(null)

    try {
      await resetUserPassword(
        accessToken,
        selectedUser.id,
        newPassword,
      )

      setNewPassword('')
      setConfirmPassword('')

      setSuccessMessage(
        `Das Passwort für ${selectedUser.first_name} ` +
          `${selectedUser.last_name} wurde zurückgesetzt.`,
      )
    } catch (error) {
      handleRequestError(
        error,
        'Das Passwort konnte nicht zurückgesetzt werden.',
      )
    } finally {
      setIsResettingPassword(false)
    }
  }

  return (
    <div className="page admin-page">
      <header className="page-header">
        <div>
          <p className="eyebrow">
            Administration
          </p>

          <h1>Benutzerverwaltung</h1>

          <p className="muted">
            Stammdaten, Zugriffsstatus und
            Administratorrechte verwalten.
          </p>
        </div>
        <button
          className="button button-primary"
          type="button"
          onClick={startCreatingUser}
        >
          Neuer Benutzer
        </button>
      </header>

      {isLoading && (
        <section className="card">
          <p className="muted">
            Benutzer werden geladen …
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

      {!isLoading && users.length === 0 && (
        <section className="card">
          <h2>Keine Benutzer vorhanden</h2>

          <p className="muted">
            Es wurden keine Benutzer gefunden.
          </p>
        </section>
      )}

      {!isLoading && users.length > 0 && (
        <section className="card">
          <label className="checkbox-field">
            <input
              type="checkbox"
              checked={hideInactiveUsers}
              onChange={(event) =>
                setHideInactiveUsers(
                  event.target.checked,
                )
              }
            />

            Inaktive Benutzer ausblenden
          </label>
        </section>
      )}

      {!isLoading && users.length > 0 && (
        <div className="admin-layout admin-users-layout">
          <section className="card table-card">
            <div className="table-scroll">
              <table className="data-table admin-users-table">
                <thead>
                  <tr>
                    <th>Name</th>
                    <th>E-Mail</th>
                    <th>Letzte Anmeldung</th>
                    <th>Status</th>
                    <th>Rolle</th>
                    <th />
                  </tr>
                </thead>

                <tbody>
                  {visibleUsers.map((managedUser) => (
                    <tr
                      key={managedUser.id}
                      className={
                        managedUser.id ===
                        selectedUserId
                          ? 'data-table-row-selected'
                          : undefined
                      }
                    >
                      <td>
                        <strong>
                          {managedUser.first_name}{' '}
                          {managedUser.last_name}
                        </strong>
                      </td>

                      <td>{managedUser.email}</td>

                      <td>
                        {formatLastLogin(
                          managedUser.last_login,
                        )}
                      </td>

                      <td>
                        <span
                          className={
                            managedUser.active
                              ? 'status-badge status-active'
                              : 'status-badge status-inactive'
                          }
                        >
                          {managedUser.active
                            ? 'Aktiv'
                            : 'Inaktiv'}
                        </span>
                      </td>

                      <td>
                        {managedUser.is_admin
                          ? 'Administrator'
                          : 'Benutzer'}
                      </td>

                      <td>
                        <button
                          className="button button-secondary"
                          type="button"
                          onClick={() =>
                            selectUser(managedUser.id)
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
          </section>

          {(isCreating ||
            selectedUser !== null) && (
            <section className="card admin-editor admin-user-editor">
              <div>
                <p className="eyebrow">
                  {isCreating
                    ? 'Neuanlage'
                    : `Benutzer #${selectedUser?.id}`}
                </p>

                <h2>
                  {isCreating
                    ? 'Neuer Benutzer'
                    : `${selectedUser?.first_name} ${selectedUser?.last_name}`}
                </h2>
              </div>

              <form
                className="admin-form"
                onSubmit={handleSaveUser}
              >
                <div className="form-grid">
                  <label className="form-field">
                    Vorname
                    <input
                      type="text"
                      value={firstName}
                      required
                      maxLength={100}
                      onChange={(event) =>
                        setFirstName(
                          event.target.value,
                        )
                      }
                    />
                  </label>

                  <label className="form-field">
                    Nachname
                    <input
                      type="text"
                      value={lastName}
                      required
                      maxLength={100}
                      onChange={(event) =>
                        setLastName(
                          event.target.value,
                        )
                      }
                    />
                  </label>
                </div>

                <label className="form-field">
                  E-Mail-Adresse
                  <input
                    type="email"
                    value={email}
                    required
                    maxLength={255}
                    onChange={(event) =>
                      setEmail(event.target.value)
                    }
                  />
                </label>

                <label className="form-field">
                  Anschrift
                  <textarea
                    value={address}
                    maxLength={500}
                    rows={4}
                    onChange={(event) =>
                      setAddress(event.target.value)
                    }
                  />
                </label>

                {isCreating && (
                  <p className="form-hint">
                    Nach dem Anlegen erhält der Benutzer
                    eine signierte E-Mail mit einem
                    einmaligen Link, über den er sein
                    persönliches Passwort festlegt.
                  </p>
                )}

                <div>
                  <p className="form-label">
                    Rechnungszustellung
                  </p>

                  <div className="checkbox-group">
                  <label className="checkbox-field">
                    <input
                      type="radio"
                      name="admin-invoice-delivery-method"
                      value="email"
                      checked={invoiceDeliveryMethod === 'email'}
                      onChange={() =>
                        setInvoiceDeliveryMethod('email')
                      }
                    />

                    Per E-Mail
                  </label>

                  <label className="checkbox-field">
                    <input
                      type="radio"
                      name="admin-invoice-delivery-method"
                      value="post"
                      checked={invoiceDeliveryMethod === 'post'}
                      onChange={() =>
                        setInvoiceDeliveryMethod('post')
                      }
                    />

                    Per Brief (Porto wird berechnet)
                  </label>

                  <label className="checkbox-field">
                    <input
                      type="radio"
                      name="admin-invoice-delivery-method"
                      value="portal"
                      checked={invoiceDeliveryMethod === 'portal'}
                      onChange={() =>
                        setInvoiceDeliveryMethod('portal')
                      }
                    />

                    Manueller Download aus dem Portal
                    nach Benachrichtigung per E-Mail
                  </label>
                  </div>
                </div>
                <div className="checkbox-group">
                  <label className="checkbox-field">
                    <input
                      type="checkbox"
                      checked={active}
                      disabled={isOwnAccount}
                      onChange={(event) =>
                        setActive(
                          event.target.checked,
                        )
                      }
                    />

                    Benutzer ist aktiv
                  </label>

                  <label className="checkbox-field">
                    <input
                      type="checkbox"
                      checked={isAdmin}
                      disabled={isOwnAccount}
                      onChange={(event) =>
                        setIsAdmin(
                          event.target.checked,
                        )
                      }
                    />

                    Administratorrechte
                  </label>
                </div>

                {isOwnAccount && (
                  <p className="form-hint">
                    Der eigene Zugang kann hier nicht
                    deaktiviert oder zum normalen
                    Benutzer herabgestuft werden.
                  </p>
                )}

                <div className="form-actions">
                  <button
                    className="button button-primary"
                    type="submit"
                    disabled={isSaving}
                  >
                    {isSaving
                      ? isCreating
                        ? 'Wird angelegt …'
                        : 'Wird gespeichert …'
                      : isCreating
                        ? 'Benutzer anlegen'
                        : 'Benutzer speichern'}
                  </button>
                </div>
              </form>

              {!isCreating &&
                selectedUser !== null && (
                  <>

                   <div className="admin-divider" />

                   <div>
                     <h2>Passwort zurücksetzen</h2>

                     <p className="muted">
                       Das neue Passwort muss mindestens
                       {' '}{passwordMinLength} Zeichen lang
                       sein.
                     </p>
                   </div>

                   <form
                     className="admin-form"
                     onSubmit={handlePasswordReset}
                   >
                     <label className="form-field">
                       Neues Passwort
                       <input
                         type="password"
                         value={newPassword}
                         required
                         minLength={passwordMinLength}
                         autoComplete="new-password"
                         onChange={(event) =>
                           setNewPassword(
                             event.target.value,
                           )
                         }
                       />
                     </label>

                     <label className="form-field">
                       Passwort wiederholen
                       <input
                         type="password"
                         value={confirmPassword}
                         required
                         minLength={passwordMinLength}
                         autoComplete="new-password"
                         onChange={(event) =>
                           setConfirmPassword(
                             event.target.value,
                           )
                         }
                       />
                     </label>

                     <div className="form-actions">
                       <button
                         className="button button-secondary"
                         type="submit"
                         disabled={isResettingPassword}
                       >
                         {isResettingPassword
                           ? 'Wird zurückgesetzt …'
                           : 'Passwort zurücksetzen'}
                       </button>
                     </div>
                   </form>
                </>
              )}
            </section>
          )}
        </div>
      )}
    </div>
  )
}

export default AdminUsersPage
