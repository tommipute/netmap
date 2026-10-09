// Giro di prova di un'installazione vera: accesso, dati inseriti dal modulo e dall'API, scheda device, mappa,
// ricerca, pagine di amministrazione, lingua inglese. Lascia il database com'era (cancella quello che crea).
//
// Variabili: NETMAP_USER / NETMAP_PASSWORD (se non c'è ancora nessun utente crea l'amministratore con questi dati),
// NETMAP_EXPECT_VERSION (versione che deve essere installata), NETMAP_TEST_BACKUP=1 (prova anche "Backup ora":
// serve lo script dell'updater attivo sul server).
import { expect, test } from '@playwright/test'

const USER = process.env.NETMAP_USER || 'admin'
const PASSWORD = process.env.NETMAP_PASSWORD || 'ProvaE2E-2026'
const VERSION = process.env.NETMAP_EXPECT_VERSION || ''
const RUN = `e2e-${Date.now().toString(36)}`
const created = { devices: [], maps: [], sites: [] }

test.describe.configure({ mode: 'serial' })

async function login(page) {
  await page.goto('/')
  await page.locator('.login__card h1').waitFor()
  await page.getByLabel('Nome utente').fill(USER)
  const passwords = page.locator('input[type=password]')
  await passwords.nth(0).fill(PASSWORD)
  if (await page.getByLabel('Ripeti la password').count()) await page.getByLabel('Ripeti la password').fill(PASSWORD)
  await page.locator('.login__card button[type=submit]').click()
  await expect(page.locator('.appfoot')).toBeVisible()
}

async function post(page, path, data) {
  const response = await page.request.post(`/api${path}`, { data })
  expect(response.ok(), `${path}: ${response.status()} ${await response.text()}`).toBeTruthy()
  return response.json()
}

test.afterAll(async ({ browser }) => {
  const page = await browser.newPage()
  await login(page)
  for (const id of created.maps) await page.request.delete(`/api/maps/${id}`)
  for (const id of created.devices) await page.request.delete(`/api/devices/${id}`)
  for (const id of created.sites) await page.request.delete(`/api/sites/${id}`)
  await page.close()
})

test('pagina di accesso: versione e link al codice sorgente', async ({ page }) => {
  await page.goto('/')
  const version = page.locator('.login__version')
  await expect(version).toContainText('NetMap')
  const source = version.getByRole('link', { name: 'Codice sorgente' })
  await expect(source).toHaveAttribute('href', /^https:\/\/github\.com\/tommipute\/netmap/)
  if (VERSION) {
    await expect(version).toContainText(VERSION)
    await expect(source).toHaveAttribute('href', new RegExp(`/tree/v${VERSION.replace(/\./g, '\\.')}$`))
  }
})

test('accesso e sede creata dal modulo', async ({ page }) => {
  await login(page)
  await page.goto('/sites')
  await page.getByRole('button', { name: 'Nuova sede' }).click()
  const dialog = page.getByRole('dialog')
  await dialog.getByLabel(/^Nome/).fill(`${RUN} sede`)
  await dialog.getByRole('button', { name: 'Crea' }).click()
  await expect(dialog).toBeHidden()
  const sites = await (await page.request.get(`/api/sites?q=${RUN}`)).json()
  created.sites.push(...sites.items.map((site) => site.id))
  expect(sites.total).toBe(1)
  await expect(page.getByRole('cell', { name: `${RUN} sede`, exact: true })).toBeVisible()
})

test('device collegati: scheda, mappa e ricerca', async ({ page }) => {
  await login(page)
  const site = created.sites[0]
  const core = await post(page, '/devices', { name: `${RUN}-core`, site_id: site, serial: `${RUN}-SN1` })
  const access = await post(page, '/devices', { name: `${RUN}-access`, site_id: site })
  created.devices.push(core.id, access.id)
  const a = await post(page, '/interfaces', { device_id: core.id, name: 'Gi1/0/1' })
  const b = await post(page, '/interfaces', { device_id: access.id, name: 'Gi1/0/48' })
  await post(page, '/cables', { a_interface_id: a.id, b_interface_id: b.id })

  await page.goto(`/devices/${core.id}`)
  await expect(page.getByRole('heading', { name: `${RUN}-core` })).toBeVisible()
  await expect(page.getByText('Gi1/0/1', { exact: true })).toBeVisible()
  await expect(page.getByRole('link', { name: `${RUN}-access` }).first()).toBeVisible()

  const map = await post(page, '/maps', { name: `${RUN} mappa`, site_id: site, auto_include: true })
  created.maps.push(map.id)
  await page.goto(`/maps/${map.id}`)
  await expect(page.locator('.react-flow__node').filter({ hasText: `${RUN}-core` })).toBeVisible()
  await expect(page.locator('.react-flow__node').filter({ hasText: `${RUN}-access` })).toBeVisible()
  await expect(page.locator('.react-flow__edge')).toHaveCount(1)

  await page.goto(`/search?q=${RUN}-SN1`)
  await expect(page.getByRole('link', { name: `${RUN}-core` }).first()).toBeVisible()
})

test('amministrazione: aggiornamenti e backup', async ({ page }) => {
  await login(page)
  await page.goto('/updates')
  await expect(page.getByRole('heading', { name: 'Aggiornamenti', level: 1 })).toBeVisible()
  if (VERSION) await expect(page.locator('.update-facts')).toContainText(VERSION)
  await page.goto('/backup')
  await expect(page.getByRole('heading', { name: 'Backup', level: 1 })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Copie fuori dal server' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Chiave dei segreti' })).toBeVisible()
  if (process.env.NETMAP_TEST_BACKUP !== '1') return
  // Lo script gira ogni minuto e la pagina si aggiorna da sola; conto solo i backup fatti a mano (nel frattempo
  // può partire anche quello notturno)
  test.setTimeout(240_000)
  const manual = page.locator('.table tbody tr').filter({ hasText: 'A mano' })
  const before = await manual.count()
  await page.getByRole('button', { name: 'Backup ora' }).click()
  await expect(manual).toHaveCount(before + 1, { timeout: 180_000 })
  await expect(page.locator('.update-live').first()).toContainText('Riuscito')
})

test('interfaccia in inglese', async ({ page }) => {
  await login(page)
  await page.evaluate(() => window.localStorage.setItem('netmap.lang', 'en'))
  await page.goto('/devices')
  await expect(page.getByRole('heading', { name: 'Devices', level: 1 })).toBeVisible()
  await expect(page.getByRole('link', { name: 'Source code' })).toBeVisible()
})
