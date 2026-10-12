import { useEffect, useRef } from 'react'
import { createPortal } from 'react-dom'

import { useTranslation } from '../i18n/useTranslation'

interface SystemMessageProps {
  kind: 'error' | 'success'
  message: string | null
  // wird mit "OK" (oder Escape) aufgerufen; setzt die Meldung zurück
  onClose: () => void
}

/*
 * Systemmeldung als Dialog mit OK-Button – unabhängig davon, wie weit die
 * Seite gescrollt ist. Ohne Meldung wird nichts angezeigt.
 */
function SystemMessage({ kind, message, onClose }: SystemMessageProps) {
  const { t } = useTranslation()
  const buttonRef = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    if (message === null) {
      return
    }

    buttonRef.current?.focus()

    function handleKeyDown(event: KeyboardEvent): void {
      if (event.key === 'Escape') {
        event.preventDefault()
        onClose()
      }
    }

    document.addEventListener('keydown', handleKeyDown)

    return () => {
      document.removeEventListener('keydown', handleKeyDown)
    }
  }, [message, onClose])

  if (message === null || message === '') {
    return null
  }

  const titleId = `system-message-title-${kind}`

  return createPortal(
    <div className="system-message-backdrop">
      <div
        className={`system-message system-message-${kind}`}
        role="alertdialog"
        aria-modal="true"
        aria-labelledby={titleId}
      >
        <h2 id={titleId}>
          {kind === 'error'
            ? t('systemMessage.errorTitle')
            : t('systemMessage.successTitle')}
        </h2>

        <p>{message}</p>

        <div className="system-message-actions">
          <button
            ref={buttonRef}
            className="button button-primary"
            type="button"
            onClick={onClose}
          >
            {t('systemMessage.ok')}
          </button>
        </div>
      </div>
    </div>,
    document.body,
  )
}

export default SystemMessage
