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
import { getDisplayLocale } from '../utils/dateFormat'
import { useTranslation } from '../i18n/useTranslation'
import { useAppSettings } from '../settings/useAppSettings'

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
  neverText: string,
): string {
  if (value === null) {
    return neverText
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

  return new Intl.DateTimeFormat(getDisplayLocale(), {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(date)
}

function AdminUsersPage() {
  const { t } = useTranslation()
  const { defaultLanguage } = useAppSettings()
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
  // '' = Standardsprache des Mandanten
  const [language, setLanguage] = useState('')
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
          t('users.loadFailed'),
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
      setLanguage('')
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
      setLanguage('')
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
    setLanguage(selectedUser.language ?? '')
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
            language: language || null,
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
          t('users.created', {
            name: `${createdUser.first_name} ${createdUser.last_name}`,
          }),
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
          language: language || null,
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
        t('users.saved', {
          name: `${updatedUser.first_name} ${updatedUser.last_name}`,
        }),
      )
    } catch (error) {
      handleRequestError(
        error,
        isCreating
          ? t('users.createFailed')
          : t('users.saveFailed'),
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
        t('users.resetPassword.minLength', {
          count: passwordMinLength,
        }),
      )

      return
    }

    if (newPassword !== confirmPassword) {
      setErrorMessage(
        t('resetPassword.mismatch'),
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
        t('users.passwordReset', {
          name: `${selectedUser.first_name} ${selectedUser.last_name}`,
        }),
      )
    } catch (error) {
      handleRequestError(
        error,
        t('users.passwordResetFailed'),
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
            {t('common.administration')}
          </p>

          <h1>{t('users.title')}</h1>

          <p className="muted">
            {t('users.intro')}
          </p>
        </div>
        <button
          className="button button-primary"
          type="button"
          onClick={startCreatingUser}
        >
          {t('users.new')}
        </button>
      </header>

      {isLoading && (
        <section className="card">
          <p className="muted">
            {t('users.loading')}
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
          <h2>{t('users.empty.title')}</h2>

          <p className="muted">
            {t('users.empty.text')}
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

            {t('users.hideInactive')}
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
                    <th>{t('users.col.name')}</th>
                    <th>{t('users.col.email')}</th>
                    <th>{t('users.col.lastLogin')}</th>
                    <th>{t('users.col.status')}</th>
                    <th>{t('users.col.role')}</th>
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
                          t('users.never'),
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
                            ? t('common.active')
                            : t('common.inactive')}
                        </span>
                      </td>

                      <td>
                        {managedUser.is_admin
                          ? t('users.role.admin')
                          : t('users.role.user')}
                      </td>

                      <td>
                        <button
                          className="button button-secondary"
                          type="button"
                          onClick={() =>
                            selectUser(managedUser.id)
                          }
                        >
                          {t('common.edit')}
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
                    ? t('users.form.creating')
                    : t('users.form.userNumber', { id: selectedUser?.id ?? '' })}
                </p>

                <h2>
                  {isCreating
                    ? t('users.new')
                    : `${selectedUser?.first_name} ${selectedUser?.last_name}`}
                </h2>
              </div>

              <form
                className="admin-form"
                onSubmit={handleSaveUser}
              >
                <div className="form-grid">
                  <label className="form-field">
                    {t('profile.firstName')}
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
                    {t('profile.lastName')}
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
                  {t('common.email')}
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
                  {t('profile.address')}
                  <textarea
                    value={address}
                    maxLength={500}
                    rows={4}
                    onChange={(event) =>
                      setAddress(event.target.value)
                    }
                  />
                </label>

                <label className="form-field">
                  {t('common.language')}
                  <select
                    value={language}
                    onChange={(event) =>
                      setLanguage(event.target.value)
                    }
                  >
                    <option value="">
                      {t('common.language.systemDefault', {
                        language: t(
                          defaultLanguage === 'en'
                            ? 'language.en'
                            : 'language.de',
                        ),
                      })}
                    </option>
                    <option value="de">{t('language.de')}</option>
                    <option value="en">{t('language.en')}</option>
                  </select>
                  <small className="muted">
                    {t('users.form.languageHint')}
                  </small>
                </label>

                {isCreating && (
                  <p className="form-hint">
                    {t('users.form.inviteHint')}
                  </p>
                )}

                <div>
                  <p className="form-label">
                    {t('users.form.delivery')}
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

                    {t('profile.delivery.email')}
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

                    {t('profile.delivery.post')}
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

                    {t('profile.delivery.portal')}
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

                    {t('users.form.active')}
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

                    {t('users.form.admin')}
                  </label>
                </div>

                {isOwnAccount && (
                  <p className="form-hint">
                    {t('users.form.ownAccountHint')}
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
                        ? t('users.form.creatingBusy')
                        : t('common.saving')
                      : isCreating
                        ? t('users.form.create')
                        : t('users.form.save')}
                  </button>
                </div>
              </form>

              {!isCreating &&
                selectedUser !== null && (
                  <>

                   <div className="admin-divider" />

                   <div>
                     <h2>{t('users.resetPassword.title')}</h2>

                     <p className="muted">
                       {t('users.resetPassword.minLength', {
                         count: passwordMinLength,
                       })}
                     </p>
                   </div>

                   <form
                     className="admin-form"
                     onSubmit={handlePasswordReset}
                   >
                     <label className="form-field">
                       {t('passwordFields.new')}
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
                       {t('passwordFields.confirm')}
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
                           ? t('users.resetPassword.submitting')
                           : t('users.resetPassword.title')}
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
