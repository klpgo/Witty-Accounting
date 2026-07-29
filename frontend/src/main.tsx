import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'

import { AppSettingsProvider } from './settings/AppSettingsProvider'

import App from './App'
import { AuthProvider } from './auth/AuthProvider'
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
          <App />
        </AuthProvider>
      </AppSettingsProvider>
    </BrowserRouter>
  </StrictMode>,
)
