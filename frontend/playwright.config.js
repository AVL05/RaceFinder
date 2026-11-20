import { defineConfig } from '@playwright/test'
import os from 'node:os'
import path from 'node:path'

// Biblioteca aislada y nueva en cada ejecución: nunca toca tu carpeta data/.
const dataDir = path.join(os.tmpdir(), `racefinder-e2e-${Date.now()}`)
const PORT = 8123
const channel = process.env.RACEFINDER_E2E_CHANNEL || undefined

export default defineConfig({
  testDir: './e2e',
  outputDir: './test-results',
  timeout: 180_000,
  workers: 1,
  fullyParallel: false,
  reporter: [['list']],
  globalSetup: './e2e/global-setup.js',
  use: { baseURL: `http://127.0.0.1:${PORT}`, channel, viewport: { width: 1440, height: 900 }, trace: 'retain-on-failure' },
  webServer: {
    // misma ruta que `pnpm start`: la API sirve la interfaz compilada
    command: `node ../scripts/dev.mjs --prod`,
    env: {
      RACEFINDER_DATA: dataDir,
      RACEFINDER_NO_OPEN: '1',
      RACEFINDER_API_PORT_START: String(PORT),
      RACEFINDER_GPU: '0',
      RACEFINDER_DEVICE: 'cpu',
      RACEFINDER_FACE_DEVICE: 'cpu',
    },
    url: `http://127.0.0.1:${PORT}/api/health`,
    reuseExistingServer: false,
    // The first run also creates the Python environment and installs its dependencies.
    timeout: 300_000,
    stdout: 'pipe',
  },
})
