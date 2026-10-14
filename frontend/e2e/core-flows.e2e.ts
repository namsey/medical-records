import { join } from 'node:path'
import { expect, test, type Page } from '@playwright/test'

// Core flows against the real app at 390px (see playwright.config.ts). The steps run in order on one database:
// the first test adds a record of every type, and the later ones view, edit, delete, search and filter them.
test.describe.configure({ mode: 'serial' })

const PDF = join(import.meta.dirname, 'fixtures', 'report.pdf')
const PNG = join(import.meta.dirname, 'fixtures', 'xray.png')
const THIS_YEAR = String(new Date().getFullYear())

interface NewRecord {
  type: string
  title: string
  file: string
  /** Fill in the fields this type requires (or that later steps search for). */
  fill?: (page: Page) => Promise<void>
  /** A date other than today, as YYYY-MM-DD, with the label of the date field. */
  date?: { label: string; value: string }
}

const RECORDS: NewRecord[] = [
  { type: 'Doctor Visit', title: 'E2E Doctor Visit', file: PDF, fill: (page) => page.getByLabel('Reason for visit').fill('Persistent cough') },
  { type: 'Prescription', title: 'E2E Prescription', file: PNG, fill: (page) => page.getByLabel('Name', { exact: true }).fill('Thyronorm') },
  { type: 'Lab Report', title: 'E2E Lab Report', file: PDF, fill: (page) => page.getByLabel('Test name').fill('Vitamin B12') },
  { type: 'Diagnosis', title: 'E2E Diagnosis', file: PNG, fill: (page) => page.getByRole('textbox', { name: /^Diagnosis/ }).fill('Hypothyroidism') },
  { type: 'Medical Document', title: 'E2E Medical Document', file: PDF },
  { type: 'Scan', title: 'E2E Scan', file: PNG, date: { label: 'Scan date', value: '2025-03-15' } },
  { type: 'Other', title: 'E2E Other', file: PDF },
]

const nav = (page: Page) => page.getByRole('navigation', { name: 'Main' })

async function openRecord(page: Page, title: string) {
  await page.goto('/records')
  await page.getByRole('link', { name: new RegExp(title.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')) }).click()
  await expect(page.getByRole('heading', { level: 1, name: title })).toBeVisible()
}

test('adds a record of each type with an attachment', async ({ page }) => {
  test.setTimeout(120_000)
  await page.goto('/')
  for (const record of RECORDS) {
    await nav(page).getByRole('button', { name: 'Add record' }).click()
    await page.getByRole('dialog', { name: 'Add record' }).getByRole('link', { name: record.type }).click()
    await expect(page.getByLabel('Record type')).toHaveValue(new RegExp(`^${record.type.toLowerCase().replace(' ', '_')}$`))

    await page.getByLabel('Title').fill(record.title)
    if (record.date) await page.getByLabel(record.date.label).fill(record.date.value)
    await record.fill?.(page)
    await page.locator('input[type=file][multiple]').setInputFiles(record.file)
    await page.getByRole('button', { name: 'Save record' }).click()

    await expect(page).toHaveURL(/\/records\/[\w-]+$/)
    await expect(page.getByRole('heading', { level: 1, name: record.title })).toBeVisible()
    const fileName = record.file === PDF ? 'report.pdf' : 'xray.png'
    await expect(page.getByText(fileName, { exact: true })).toBeVisible()
  }

  await page.goto('/records')
  await expect(page.getByText(`${RECORDS.length} records`, { exact: true })).toBeVisible()
})

test('views a record and opens its attachment', async ({ page }) => {
  await openRecord(page, 'E2E Scan')
  await expect(page.locator('dt', { hasText: 'Scan date' }).locator('+ dd')).toHaveText('15 Mar 2025')

  await page.getByRole('link', { name: 'View' }).click()
  await expect(page.getByRole('heading', { level: 1, name: 'xray.png' })).toBeVisible()
  const image = page.getByRole('img', { name: 'xray.png' })
  await expect(image).toBeVisible()
  // The image actually decoded (not just an empty <img>).
  expect(await image.evaluate((img) => (img as { naturalWidth: number }).naturalWidth)).toBeGreaterThan(0)
})

test('edits a record', async ({ page }) => {
  await openRecord(page, 'E2E Other')
  await page.getByRole('link', { name: 'Edit record' }).click()
  await page.getByLabel('Title').fill('E2E Other (edited)')
  await page.getByRole('button', { name: 'Save changes' }).click()
  await expect(page.getByRole('heading', { level: 1, name: 'E2E Other (edited)' })).toBeVisible()
})

test('deletes a record', async ({ page }) => {
  await openRecord(page, 'E2E Other (edited)')
  await page.getByRole('button', { name: 'Delete record' }).click()
  await page.getByRole('dialog', { name: 'Delete this record?' }).getByRole('button', { name: 'Delete', exact: true }).click()

  await expect(page).toHaveURL(/\/records$/)
  await expect(page.getByText(`${RECORDS.length - 1} records`, { exact: true })).toBeVisible()
  await expect(page.getByRole('link', { name: /E2E Other/ })).toHaveCount(0)
})

test('searches records', async ({ page }) => {
  await page.goto('/')
  await nav(page).getByRole('link', { name: 'Search' }).click()
  await page.getByRole('searchbox', { name: 'Search records' }).fill('thyronorm')
  await expect(page.getByText('1 record found', { exact: true })).toBeVisible()
  await expect(page.getByRole('link', { name: /E2E Prescription/ })).toBeVisible()
})

test('filters records by type and year', async ({ page }) => {
  await page.goto('/records')
  const chips = page.getByRole('group', { name: 'Quick filters' })

  await chips.getByRole('button', { name: 'Lab Report' }).click()
  await expect(page.getByText('1 lab report', { exact: true })).toBeVisible()
  await expect(page.getByRole('link', { name: /E2E Lab Report/ })).toBeVisible()

  await chips.getByRole('button', { name: 'All' }).click()
  await chips.getByRole('button', { name: '2025' }).click()
  await expect(page.getByText('1 record in 2025', { exact: true })).toBeVisible()
  await expect(page.getByRole('link', { name: /E2E Scan/ })).toBeVisible()

  await chips.getByRole('button', { name: 'All' }).click()
  await expect(page.getByText(`${RECORDS.length - 1} records`, { exact: true })).toBeVisible()
})

test('switches between List and Timeline', async ({ page }) => {
  await page.goto('/records')
  const views = page.getByRole('tablist', { name: 'Browse records as' })

  await views.getByRole('tab', { name: 'Timeline' }).click()
  await expect(page).toHaveURL(/\/timeline$/)
  await expect(page.getByRole('heading', { name: THIS_YEAR, exact: true })).toBeVisible()
  await expect(page.getByRole('heading', { name: '2025', exact: true })).toBeVisible()
  await expect(page.getByRole('link', { name: /E2E Scan/ })).toBeVisible()

  await views.getByRole('tab', { name: 'List' }).click()
  await expect(page).toHaveURL(/\/records$/)
  await expect(page.getByRole('heading', { name: 'March 2025' })).toBeVisible()
})
