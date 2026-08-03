import { readFileSync } from 'node:fs'

import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const packageJson = JSON.parse(
  readFileSync(
    new URL('./package.json', import.meta.url),
    'utf-8',
  ),
) as { version: string }

export default defineConfig({
  plugins: [react()],
  define: {
    __FRONTEND_VERSION__: JSON.stringify(
      packageJson.version,
    ),
  },
  server: {
    host: '0.0.0.0',
    allowedHosts: [
      'dock.kgem.de',
    ],
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})
