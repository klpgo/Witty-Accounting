import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'

import {
  listWallboxes,
  SettingsApiError,
  updateWallboxName,
  type Wallbox,
} from '../api/settings'
import { getAccessToken } from '../auth/tokenStorage'
import { useAuth } from '../auth/useAuth'
import { useTranslation } from '../i18n/useTranslation'
import { formatDate } from '../utils/dateFormat'

/*
 * Namen der Wallboxen für Ladevorgänge und Rechnungen. Angezeigt wird der
 * eigene Name, sonst der Name aus der Hager Cloud, sonst "ID: ..XXXXX".
 */
function AdminWallboxesForm() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const { signOut } = useAuth()

  const [wallboxes, setWallboxes] = useState<Wallbox[]>([])
  const [drafts, setDrafts] = useState<Record<number, string>>({})
  const [isLoading, setIsLoading] = useState(true)
  const [savingId, setSavingId] = useState<number | null>(null)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)
  const [successMessage, setSuccessMessage] = useState<string | null>(null)

  const handleUnauthorized = useCallback((): void => {
    signOut()
    navigate('/login', { replace: true })
  }, [navigate, signOut])

  useEffect(() => {
    const controller = new AbortController()

    async function load(): Promise<void> {
      const accessToken = getAccessToken()

      if (accessToken === null) {
        handleUnauthorized()
        return
      }

      try {
        const loaded = await listWallboxes(accessToken, controller.signal)
        setWallboxes(loaded)
        setDrafts(
          Object.fromEntries(
            loaded.map((wallbox) => [wallbox.id, wallbox.custom_name ?? '']),
          ),
        )
      } catch (error) {
        if (error instanceof DOMException && error.name === 'AbortError') {
          return
        }

        if (error instanceof SettingsApiError && error.status === 401) {
          handleUnauthorized()
          return
        }

        setErrorMessage(
          error instanceof Error ? error.message : t('wallboxes.loadFailed'),
        )
      } finally {
        if (!controller.signal.aborted) {
          setIsLoading(false)
        }
      }
    }

    void load()

    return () => {
      controller.abort()
    }
  }, [handleUnauthorized, t])

  async function save(wallbox: Wallbox): Promise<void> {
    const accessToken = getAccessToken()

    if (accessToken === null) {
      handleUnauthorized()
      return
    }

    setSavingId(wallbox.id)
    setErrorMessage(null)
    setSuccessMessage(null)

    try {
      const updated = await updateWallboxName(
        accessToken,
        wallbox.id,
        drafts[wallbox.id] ?? '',
      )

      setWallboxes((current) =>
        current.map((entry) => (entry.id === updated.id ? updated : entry)),
      )
      setDrafts((current) => ({
        ...current,
        [updated.id]: updated.custom_name ?? '',
      }))
      setSuccessMessage(
        t('wallboxes.saved', {
          name: updated.display_name,
          count: updated.updated_sessions,
        }),
      )
    } catch (error) {
      if (error instanceof SettingsApiError && error.status === 401) {
        handleUnauthorized()
        return
      }

      setErrorMessage(
        error instanceof Error ? error.message : t('wallboxes.saveFailed'),
      )
    } finally {
      setSavingId(null)
    }
  }

  return (
    <section className="card settings-form">
      <div className="settings-section">
        <div>
          <h2>{t('wallboxes.title')}</h2>
          <p className="muted">{t('wallboxes.intro')}</p>
        </div>

        {errorMessage && (
          <p className="form-error" role="alert">
            {errorMessage}
          </p>
        )}

        {successMessage && (
          <p className="form-success" role="status">
            {successMessage}
          </p>
        )}

        {isLoading ? (
          <p className="muted">{t('common.loading')}</p>
        ) : wallboxes.length === 0 ? (
          <p className="muted">{t('wallboxes.none')}</p>
        ) : (
          <div className="table-scroll">
            <table className="data-table compact-table">
              <thead>
                <tr>
                  <th>{t('wallboxes.col.id')}</th>
                  <th>{t('wallboxes.col.hagerName')}</th>
                  <th>{t('wallboxes.col.customName')}</th>
                  <th className="table-number">{t('wallboxes.col.sessions')}</th>
                  <th>{t('wallboxes.col.lastSession')}</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {wallboxes.map((wallbox) => {
                  const draft = drafts[wallbox.id] ?? ''
                  const changed = draft.trim() !== (wallbox.custom_name ?? '')

                  return (
                    <tr key={wallbox.id}>
                      <td title={wallbox.wallbox_id}>
                        {`..${wallbox.wallbox_id.slice(-5)}`}
                      </td>
                      <td>{wallbox.hager_name ?? '–'}</td>
                      <td>
                        <input
                          type="text"
                          value={draft}
                          maxLength={100}
                          placeholder={wallbox.display_name}
                          aria-label={t('wallboxes.col.customName')}
                          disabled={savingId === wallbox.id}
                          onChange={(event) => {
                            setDrafts((current) => ({
                              ...current,
                              [wallbox.id]: event.target.value,
                            }))
                          }}
                        />
                      </td>
                      <td className="table-number">{wallbox.session_count}</td>
                      <td>
                        {wallbox.last_session_at
                          ? formatDate(wallbox.last_session_at.slice(0, 10))
                          : '–'}
                      </td>
                      <td>
                        <button
                          className="button button-secondary"
                          type="button"
                          disabled={!changed || savingId !== null}
                          onClick={() => {
                            void save(wallbox)
                          }}
                        >
                          {savingId === wallbox.id
                            ? t('common.saving')
                            : t('wallboxes.save')}
                        </button>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </section>
  )
}

export default AdminWallboxesForm
