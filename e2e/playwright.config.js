import { defineConfig } from '@playwright/test'

// NETMAP_URL: installazione da provare (predefinito https://localhost, quella di upgrade-test.sh).
// PW_CHROMIUM: Chromium già presente sul computer, al posto di quello scaricato da "npx playwright install".
export default defineConfig({
  testDir: './tests',
  timeout: 90_000,
  expect: { timeout: 15_000 },
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  reporter: process.env.CI ? [['list'], ['html', { open: 'never' }]] : 'list',
  use: {
    baseURL: process.env.NETMAP_URL || 'https://localhost',
    ignoreHTTPSErrors: true, // CA interna di Caddy
    viewport: { width: 1300, height: 850 },
    screenshot: 'only-on-failure',
    trace: 'retain-on-failure',
    launchOptions: process.env.PW_CHROMIUM ? { executablePath: process.env.PW_CHROMIUM } : {},
  },
})
