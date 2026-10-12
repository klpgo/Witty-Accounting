import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'

import { AppSettingsProvider } from './settings/AppSettingsProvider'

import App from './App'
import { AuthProvider } from './auth/AuthProvider'
import { I18nProvider } from './i18n/I18nProvider'
import './styles.css'

const rootElement =
  document.getElementById('root')

if (rootElement === null) {
  throw new Error(
    'Das Root-Element wurde nicht gefunden.',
  )
}

createRoot(rootElement).render(
  <StrictMode>
    <BrowserRouter>
      <AppSettingsProvider>
        <AuthProvider>
          <I18nProvider>
            <App />
          </I18nProvider>
        </AuthProvider>
      </AppSettingsProvider>
    </BrowserRouter>
  </StrictMode>,
)
