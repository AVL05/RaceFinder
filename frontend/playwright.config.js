import { defineConfig } from '@playwright/test'
import os from 'node:os'
import path from 'node:path'

// Biblioteca aislada y nueva en cada ejecución: nunca toca tu carpeta data/.
const dataDir = path.join(os.tmpdir(), `racefinder-e2e-${Date.now()}`)
const PORT = 8123

export default defineConfig({
  testDir: './e2e',
  outputDir: './test-results',
  timeout: 180_000,
  workers: 1,
  fullyParallel: false,
  reporter: [['list']],
  globalSetup: './e2e/global-setup.js',
  use: { baseURL: `http://127.0.0.1:${PORT}`, viewport: { width: 1440, height: 900 }, trace: 'retain-on-failure' },
  webServer: {
    // misma ruta que `pnpm start`: la API sirve la interfaz compilada
    command: `node ../scripts/dev.mjs --prod`,
    env: { RACEFINDER_DATA: dataDir, RACEFINDER_NO_OPEN: '1', RACEFINDER_API_PORT_START: String(PORT) },
    url: `http://127.0.0.1:${PORT}/api/health`,
    reuseExistingServer: false,
    timeout: 120_000,
  },
})
