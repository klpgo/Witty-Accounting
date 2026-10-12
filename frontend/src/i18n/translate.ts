import { de, type MessageKey } from './de'
import { en } from './en'

export type Language = 'de' | 'en'
export type MessageParams = Record<string, string | number>

export const SUPPORTED_LANGUAGES: readonly Language[] = ['de', 'en']

const MESSAGES: Record<Language, Record<MessageKey, string>> = { de, en }

export function normalizeLanguage(value: string | null | undefined): Language | null {
  return value === 'de' || value === 'en' ? value : null
}

/**
 * Übersetzt einen Schlüssel. Platzhalter {name} werden ersetzt; enthält der
 * Text "Einzahl|Mehrzahl" und ist {count} gesetzt, wird die passende Form
 * über die Pluralregeln der Sprache gewählt.
 */
export function translate(
  language: Language,
  key: MessageKey,
  params?: MessageParams,
): string {
  let text: string = MESSAGES[language][key] ?? de[key] ?? key

  if (params && typeof params.count === 'number' && text.includes('|')) {
    const [one, other] = text.split('|')
    text =
      new Intl.PluralRules(language).select(params.count) === 'one'
        ? one
        : other
  }

  if (!params) {
    return text
  }

  return text.replace(/\{(\w+)\}/g, (placeholder, name: string) =>
    name in params ? String(params[name]) : placeholder,
  )
}
