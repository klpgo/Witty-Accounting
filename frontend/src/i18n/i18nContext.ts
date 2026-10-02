import { createContext } from 'react'

import type { MessageKey } from './de'
import type { Language, MessageParams } from './translate'

export interface I18nContextValue {
  language: Language
  t: (key: MessageKey, params?: MessageParams) => string
}

export const I18nContext = createContext<I18nContextValue | undefined>(
  undefined,
)
