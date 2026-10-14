import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { defineConfig } from '@playwright/test'

// End-to-end tests run the real app: the production build served by the FastAPI backend, against a throwaway
// database and upload folder (see e2e/server.py), signed in through a session the server creates at start-up.
const PORT = 8765
const DATA_DIR = process.env.E2E_DATA_DIR ?? join(tmpdir(), 'medical-records-e2e')
const STATE_FILE = join(DATA_DIR, 'storage-state.json')
// The Python that has the backend's requirements installed (e.g. backend/.venv/bin/python).
const PYTHON = process.env.E2E_PYTHON ?? (process.platform === 'win32' ? 'python' : 'python3')

export default defineConfig({
  testDir: './e2e',
  // *.e2e.ts, so Vitest (which picks up *.test.* / *.spec.*) never runs these.
  testMatch: '**/*.e2e.ts',
  // One shared database: the core-flows suite builds on its own earlier steps, so run in order.
  workers: 1,
  fullyParallel: false,
  forbidOnly: Boolean(process.env.CI),
  retries: 0,
  reporter: process.env.CI ? [['list'], ['html', { open: 'never' }]] : 'list',
  use: {
    baseURL: `http://127.0.0.1:${PORT}`,
    storageState: STATE_FILE,
    // A phone-sized screen.
    viewport: { width: 390, height: 844 },
    isMobile: true,
    hasTouch: true,
    deviceScaleFactor: 2,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  webServer: {
    command: `npm run build && ${PYTHON} e2e/server.py`,
    url: `http://127.0.0.1:${PORT}/api/health`,
    env: { E2E_DATA_DIR: DATA_DIR, E2E_STATE_FILE: STATE_FILE, E2E_PORT: String(PORT) },
    reuseExistingServer: false,
    timeout: 180_000,
    stdout: 'pipe',
  },
})
