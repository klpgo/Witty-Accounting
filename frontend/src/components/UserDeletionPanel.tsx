import { useState } from 'react'

import {
  deleteUser,
  getUserDeletionCheck,
  type User,
  type UserDeletionBlocker,
  type UserDeletionCheck,
} from '../api/users'
import { getAccessToken } from '../auth/tokenStorage'
import type { MessageKey } from '../i18n/de'
import { useTranslation } from '../i18n/useTranslation'

const BLOCKER_KEYS: Record<string, MessageKey> = {
  own_account: 'users.delete.blocker.ownAccount',
  draft_invoices: 'users.delete.blocker.draftInvoices',
  missing_invoice_pdfs: 'users.delete.blocker.missingPdfs',
  active_rfid_assignments: 'users.delete.blocker.activeAssignments',
  unbilled_charging_sessions: 'users.delete.blocker.unbilledSessions',
  unbilled_base_fees: 'users.delete.blocker.unbilledFees',
}

interface UserDeletionPanelProps {
  user: User
  onDeleted: (user: User) => void
  onError: (error: unknown, fallbackMessage: string) => void
}

function UserDeletionPanel({
  user,
  onDeleted,
  onError,
}: UserDeletionPanelProps) {
  const { t } = useTranslation()

  const [check, setCheck] =
    useState<UserDeletionCheck | null>(null)
  const [isChecking, setIsChecking] = useState(false)
  const [isDeleting, setIsDeleting] = useState(false)
  const [discardUnbilled, setDiscardUnbilled] =
    useState(false)
  const [confirmed, setConfirmed] = useState(false)

  function blockerText(blocker: UserDeletionBlocker): string {
    const key = BLOCKER_KEYS[blocker.code]

    return key === undefined
      ? blocker.message
      : t(key, { count: blocker.count })
  }

  async function handleCheck(): Promise<void> {
    const accessToken = getAccessToken()

    if (accessToken === null) {
      return
    }

    setIsChecking(true)
    setConfirmed(false)
    setDiscardUnbilled(false)

    try {
      setCheck(
        await getUserDeletionCheck(accessToken, user.id),
      )
    } catch (error) {
      onError(error, t('users.delete.checkFailed'))
    } finally {
      setIsChecking(false)
    }
  }

  async function handleDelete(): Promise<void> {
    const accessToken = getAccessToken()

    if (accessToken === null || check === null) {
      return
    }

    setIsDeleting(true)

    try {
      await deleteUser(
        accessToken,
        user.id,
        discardUnbilled,
      )
      setCheck(null)
      onDeleted(user)
    } catch (error) {
      onError(error, t('users.delete.failed'))
      // Stand neu ermitteln, falls sich inzwischen etwas geändert hat
      void handleCheck()
    } finally {
      setIsDeleting(false)
    }
  }

  const canDelete =
    check !== null &&
    (check.can_delete ||
      (discardUnbilled && check.can_delete_with_discard))

  const hasDiscardableBlockers =
    check !== null &&
    check.blockers.some((blocker) => blocker.discardable)

  return (
    <div className="user-deletion">
      <div>
        <h2>{t('users.delete.title')}</h2>

        <p className="muted">{t('users.delete.intro')}</p>
      </div>

      {check === null && (
        <div className="form-actions">
          <button
            className="button button-secondary"
            type="button"
            disabled={isChecking}
            onClick={() => {
              void handleCheck()
            }}
          >
            {isChecking
              ? t('users.delete.checking')
              : t('users.delete.check')}
          </button>
        </div>
      )}

      {check !== null && (
        <>
          <ul className="user-deletion-summary">
            <li>
              {t('users.delete.summary.sessions', {
                count: check.charging_sessions,
              })}
            </li>
            <li>
              {t('users.delete.summary.fees', {
                count: check.base_fees,
              })}
            </li>
            <li>
              {t('users.delete.summary.assignments', {
                count: check.rfid_assignments,
              })}
            </li>
            <li>
              <strong>
                {t('users.delete.summary.invoicesKept', {
                  count: check.invoices_kept,
                })}
              </strong>
            </li>
          </ul>

          {check.blockers.length > 0 && (
            <div className="form-error" role="alert">
              <p>{t('users.delete.blocked')}</p>

              <ul>
                {check.blockers.map((blocker) => (
                  <li key={blocker.code}>
                    {blockerText(blocker)}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {hasDiscardableBlockers &&
            check.can_delete_with_discard && (
              <label className="checkbox-field">
                <input
                  type="checkbox"
                  checked={discardUnbilled}
                  onChange={(event) =>
                    setDiscardUnbilled(event.target.checked)
                  }
                />

                {t('users.delete.discardUnbilled')}
              </label>
            )}

          {canDelete && (
            <label className="checkbox-field">
              <input
                type="checkbox"
                checked={confirmed}
                onChange={(event) =>
                  setConfirmed(event.target.checked)
                }
              />

              {t('users.delete.confirm', {
                name: `${user.first_name} ${user.last_name}`,
              })}
            </label>
          )}

          <div className="form-actions">
            <button
              className="button button-danger"
              type="button"
              disabled={!canDelete || !confirmed || isDeleting}
              onClick={() => {
                void handleDelete()
              }}
            >
              {isDeleting
                ? t('users.delete.deleting')
                : t('users.delete.submit')}
            </button>

            <button
              className="button button-secondary"
              type="button"
              disabled={isDeleting}
              onClick={() => setCheck(null)}
            >
              {t('common.cancel')}
            </button>
          </div>
        </>
      )}
    </div>
  )
}

export default UserDeletionPanel
