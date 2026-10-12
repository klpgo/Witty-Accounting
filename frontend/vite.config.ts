import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

const packageJson = JSON.parse(
  readFileSync(
    new URL('./package.json', import.meta.url),
    'utf-8',
  ),
) as { version: string }

export default defineConfig(({ mode }) => {
  // VITE_ALLOWED_HOSTS aus der Umgebung, aus der .env im Projektordner
  // (eine Ebene über frontend/) oder aus frontend/.env
  const env = {
    ...loadEnv(mode, fileURLToPath(new URL('..', import.meta.url)), ''),
    ...loadEnv(mode, fileURLToPath(new URL('.', import.meta.url)), ''),
    ...process.env,
  }

  return {
    plugins: [react()],
    define: {
      __FRONTEND_VERSION__: JSON.stringify(
        packageJson.version,
      ),
    },
    server: {
      host: '0.0.0.0',
      // weitere Hostnamen für den Entwicklungsserver, kommagetrennt,
      // z. B. VITE_ALLOWED_HOSTS=dev.example.org,dev2.example.org
      allowedHosts: (env.VITE_ALLOWED_HOSTS ?? '')
        .split(',')
        .map((host) => host.trim())
        .filter((host) => host.length > 0),
      proxy: {
        '/api': {
          target: 'http://localhost:8000',
          changeOrigin: true,
        },
      },
    },
  }
})
