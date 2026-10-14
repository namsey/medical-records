import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { fullRecord, mockApi, renderApp, summary, USER } from './test/helpers'

/** Matches the paragraph whose full text (across inline elements) is exactly `text`. */
const paragraph = (text: string) => (_: string, element: Element | null) => element?.tagName === 'P' && element.textContent === text

const emptyPage = { items: [], total: 0, limit: 20, offset: 0 }
const authed = { 'GET /api/auth/me': USER }

describe('authentication', () => {
  it('sends a signed-out visitor to the login page', async () => {
    mockApi({ 'GET /api/auth/me': () => ({ status: 401, json: { detail: 'Not authenticated' } }) })
    renderApp('/records')
    expect(await screen.findByRole('link', { name: /sign in with google/i })).toHaveAttribute('href', '/api/auth/login')
  })

  it('explains why a sign-in was refused', async () => {
    mockApi({ 'GET /api/auth/me': () => ({ status: 401, json: {} }) })
    renderApp('/login?error=not_allowed')
    expect(await screen.findByRole('alert')).toHaveTextContent(/not allowed/i)
  })

  it('leaves the login page once signed in', async () => {
    mockApi({ ...authed, 'GET /api/records': emptyPage })
    renderApp('/login')
    expect(await screen.findByRole('heading', { name: 'Medical Records' })).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /sign in/i })).not.toBeInTheDocument()
  })
})

describe('home and records', () => {
  it('shows recent records with type, date, doctor/lab, tags and attachment count', async () => {
    mockApi({ ...authed, 'GET /api/records': { items: [summary()], total: 1, limit: 8, offset: 0 } })
    renderApp('/')
    const card = await screen.findByRole('link', { name: /Lab Report - Vitamin B12/ })
    expect(card).toHaveAttribute('href', '/records/r1')
    expect(within(card).getByText(paragraph('Lab Report · 10 Sep 2026 · 1 file'))).toBeInTheDocument()
    expect(within(card).getByText(/Dr\. Anita Sharma · Pathcare Diagnostics/)).toBeInTheDocument()
    expect(within(card).getByText('Blood')).toBeInTheDocument()
    expect(card.querySelectorAll('svg.lucide-chevron-right')).toHaveLength(1)
    expect(screen.getByRole('link', { name: /add record/i })).toHaveAttribute('href', '/add')
    expect(screen.getByRole('link', { name: /view all \(1\)/i })).toBeInTheDocument()
  })

  it('shows an empty state when there are no records', async () => {
    mockApi({ ...authed, 'GET /api/records': emptyPage })
    renderApp('/')
    expect(await screen.findByText('No records yet')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /add your first record/i })).toBeInTheDocument()
  })

  it('shows a retry button when loading fails', async () => {
    mockApi({ ...authed, 'GET /api/records': () => ({ status: 500, json: { detail: 'Boom' } }) })
    renderApp('/')
    expect(await screen.findByRole('alert')).toHaveTextContent('Boom')
    expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument()
  })

  it('has the four main navigation entries', async () => {
    mockApi({ ...authed, 'GET /api/records': emptyPage })
    renderApp('/')
    const nav = await screen.findByRole('navigation', { name: 'Main' })
    for (const label of ['Home', 'Records', 'Add', 'Search']) {
      expect(within(nav).getByRole('link', { name: label })).toBeInTheDocument()
    }
  })

  it('leaves the file count out of the card meta when there are no files, and pluralises it', async () => {
    mockApi({ ...authed, 'GET /api/records': { items: [summary({ id: 'a', title: 'No files', document_count: 0 }), summary({ id: 'b', title: 'Two files', document_count: 2 })], total: 2, limit: 8, offset: 0 } })
    renderApp('/')
    expect(within(await screen.findByRole('link', { name: /No files/ })).getByText(paragraph('Lab Report · 10 Sep 2026'))).toBeInTheDocument()
    expect(within(screen.getByRole('link', { name: /Two files/ })).getByText(paragraph('Lab Report · 10 Sep 2026 · 2 files'))).toBeInTheDocument()
  })

  it('searches as you type and shows matches', async () => {
    const calls = mockApi({
      ...authed,
      'GET /api/records': emptyPage,
      'GET /api/search': { items: [summary({ title: 'Thyroid follow up', record_type: 'prescription' })], total: 1, limit: 20, offset: 0 },
      'GET /api/tags': [],
    })
    renderApp('/search')
    await userEvent.type(await screen.findByRole('searchbox', { name: 'Search records' }), 'thyroid')
    expect(await screen.findByText('Thyroid follow up')).toBeInTheDocument()
    await waitFor(() => expect(calls.some((c) => c.path === '/api/search')).toBe(true))
    expect(screen.getByText('1 record found')).toBeInTheDocument()
  })

  it('shows a no-results message for a search with no matches', async () => {
    mockApi({ ...authed, 'GET /api/search': emptyPage, 'GET /api/records': emptyPage, 'GET /api/tags': [] })
    renderApp('/search?q=zzz')
    expect(await screen.findByText('No matching records')).toBeInTheDocument()
  })
})

describe('adding a record', () => {
  it('offers every record type', async () => {
    mockApi(authed)
    renderApp('/add')
    for (const label of ['Doctor Visit', 'Prescription', 'Lab Report', 'Diagnosis', 'Medical Document', 'Scan', 'Other']) {
      expect(await screen.findByRole('link', { name: new RegExp(label) })).toBeInTheDocument()
    }
  })

  it('creates a doctor visit and opens it', async () => {
    const calls = mockApi({
      ...authed,
      'GET /api/doctors': [],
      'GET /api/tags': [],
      'GET /api/config': { max_upload_mb: 20, allowed_extensions: ['.pdf'] },
      'POST /api/records': () => ({ status: 201, json: fullRecord({ record_type: 'doctor_visit', title: 'Doctor Visit', summary: null, results: [], documents: [] }) }),
      'GET /api/records/r1': fullRecord({ record_type: 'doctor_visit', title: 'Doctor Visit', summary: null, results: [], documents: [], test_name: null, personal_notes: null }),
    })
    renderApp('/add/doctor_visit')
    const user = userEvent.setup()
    await user.type(await screen.findByLabelText('Reason for visit'), 'Chest pain')
    await user.type(screen.getByLabelText('Hospital / clinic'), 'City Hospital')
    await user.type(screen.getByLabelText('Tags'), 'Heart{Enter}')
    await user.click(screen.getByRole('button', { name: 'Save record' }))

    await waitFor(() => expect(calls.some((c) => c.method === 'POST' && c.path === '/api/records')).toBe(true))
    const post = calls.find((c) => c.method === 'POST' && c.path === '/api/records')!
    expect(post.headers['X-Requested-With']).toBe('XMLHttpRequest')
    expect(post.body).toMatchObject({ record_type: 'doctor_visit', reason: 'Chest pain', hospital: 'City Hospital', tags: ['Heart'], medicines: [], results: [] })
    expect(await screen.findByRole('heading', { name: 'Doctor Visit' })).toBeInTheDocument()
  })

  it('blocks saving a lab report without a test name', async () => {
    const calls = mockApi({ ...authed, 'GET /api/doctors': [], 'GET /api/labs': [], 'GET /api/tags': [], 'GET /api/config': { max_upload_mb: 20, allowed_extensions: ['.pdf'] } })
    renderApp('/add/lab_report')
    await userEvent.click(await screen.findByRole('button', { name: 'Save record' }))
    expect(await screen.findByText('Test name is required')).toBeInTheDocument()
    expect(calls.some((c) => c.method === 'POST')).toBe(false)
  })

  it('shows the server message when saving fails', async () => {
    mockApi({
      ...authed,
      'GET /api/doctors': [],
      'GET /api/tags': [],
      'GET /api/config': { max_upload_mb: 20, allowed_extensions: ['.pdf'] },
      'POST /api/records': () => ({ status: 422, json: { detail: 'Selected doctor does not exist' } }),
    })
    renderApp('/add/doctor_visit')
    await userEvent.click(await screen.findByRole('button', { name: 'Save record' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Selected doctor does not exist')
  })

  it('lets medicines be added to a prescription', async () => {
    mockApi({ ...authed, 'GET /api/doctors': [], 'GET /api/tags': [], 'GET /api/config': { max_upload_mb: 20, allowed_extensions: ['.pdf'] } })
    renderApp('/add/prescription')
    expect(await screen.findByText('Medicine 1')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: /add medicine/i }))
    expect(screen.getByText('Medicine 2')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Remove medicine 1' }))
    expect(screen.queryByText('Medicine 2')).not.toBeInTheDocument()
  })

  it('rejects unsupported attachments before uploading', async () => {
    mockApi({ ...authed, 'GET /api/doctors': [], 'GET /api/tags': [], 'GET /api/config': { max_upload_mb: 1, allowed_extensions: ['.pdf', '.jpg', '.jpeg', '.png', '.webp'] } })
    renderApp('/add/doctor_visit')
    const input = (await screen.findByText('Choose files')).closest('div')!.parentElement!.querySelector('input[type=file]') as HTMLInputElement
    const user = userEvent.setup({ applyAccept: false })
    await user.upload(input, [new File(['x'], 'notes.txt', { type: 'text/plain' }), new File(['%PDF'], 'ok.pdf', { type: 'application/pdf' })])
    expect(await screen.findByRole('alert')).toHaveTextContent('notes.txt')
    expect(screen.getByText('ok.pdf')).toBeInTheDocument()
  })
})

describe('record detail', () => {
  const routes = {
    ...authed,
    'GET /api/records/r1': fullRecord(),
    'GET /api/config': { max_upload_mb: 20, allowed_extensions: ['.pdf'] },
  }

  it('shows the facts, results, notes and attachments', async () => {
    mockApi(routes)
    renderApp('/records/r1')
    expect(await screen.findByRole('heading', { name: 'Lab Report - Vitamin B12' })).toBeInTheDocument()
    expect(screen.getByText('Test date')).toBeInTheDocument()
    expect(screen.getByText('296 pg/mL')).toBeInTheDocument()
    expect(screen.getByText('Reference: 200-900')).toBeInTheDocument()
    expect(screen.getByText('Normal')).toBeInTheDocument()
    expect(screen.getByText('Felt tired that week')).toBeInTheDocument()
    expect(screen.getByText('b12.pdf')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /view/i })).toHaveAttribute('href', '/documents/d1')
    expect(screen.getByRole('link', { name: /download/i })).toHaveAttribute('href', '/api/documents/d1/download')
  })

  it('asks for confirmation before deleting, then deletes', async () => {
    const calls = mockApi({ ...routes, 'DELETE /api/records/r1': () => ({ status: 204 }), 'GET /api/records': emptyPage })
    renderApp('/records/r1')
    const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: /delete record/i }))
    const dialog = await screen.findByRole('dialog')
    expect(dialog).toHaveTextContent(/permanently deleted/i)
    expect(calls.some((c) => c.method === 'DELETE')).toBe(false)
    await user.click(within(dialog).getByRole('button', { name: 'Delete' }))
    await waitFor(() => expect(calls.some((c) => c.method === 'DELETE' && c.path === '/api/records/r1')).toBe(true))
  })

  it('does not delete when cancelled', async () => {
    const calls = mockApi(routes)
    renderApp('/records/r1')
    const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: /delete record/i }))
    await user.click(within(await screen.findByRole('dialog')).getByRole('button', { name: 'Cancel' }))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(calls.some((c) => c.method === 'DELETE')).toBe(false)
  })

  it('reports a missing record', async () => {
    mockApi({ ...authed, 'GET /api/records/nope': () => ({ status: 404, json: { detail: 'Record not found' } }) })
    renderApp('/records/nope')
    expect(await screen.findByRole('alert')).toHaveTextContent('no longer exists')
  })
})

describe('timeline', () => {
  it('groups records by year and day, newest first', async () => {
    mockApi({
      ...authed,
      'GET /api/tags': [],
      'GET /api/timeline': [
        { id: 'a', record_type: 'lab_report', title: 'Blood Test', record_date: '2026-09-10', doctor_name: null, lab_name: 'Lab', document_count: 0 },
        { id: 'b', record_type: 'doctor_visit', title: 'Doctor Visit', record_date: '2026-09-05', doctor_name: 'Dr. A', lab_name: null, document_count: 1 },
        { id: 'c', record_type: 'prescription', title: 'Prescription', record_date: '2026-09-05', doctor_name: 'Dr. A', lab_name: null, document_count: 0 },
        { id: 'd', record_type: 'scan', title: 'MRI Report', record_date: '2025-08-20', doctor_name: null, lab_name: null, document_count: 0 },
      ],
    })
    renderApp('/timeline')
    expect(await screen.findByRole('heading', { name: '2026' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: '2025' })).toBeInTheDocument()
    expect(screen.getAllByText('05 Sep')).toHaveLength(1) // two records on one day share one date label
    expect(screen.getByText('10 Sep')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Blood Test/ })).toHaveAttribute('href', '/records/a')
  })
})

describe('doctors', () => {
  it('lists doctors and adds a new one', async () => {
    const doctors = [{ id: 'd1', name: 'Dr. Anita Sharma', specialization: 'Endocrinology', hospital: 'Sunrise Clinic', phone: '12345', email: null, address: null, notes: null, record_count: 2 }]
    const calls = mockApi({
      ...authed,
      'GET /api/doctors': doctors,
      'POST /api/doctors': (call) => ({ status: 201, json: { ...(call.body as object), id: 'd2', record_count: 0 } }),
    })
    renderApp('/doctors')
    expect(await screen.findByText('Dr. Anita Sharma')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: '12345' })).toHaveAttribute('href', 'tel:12345')
    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: /^add$/i }))
    await user.type(await screen.findByLabelText(/^Name/), 'Dr. New')
    await user.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => expect(calls.some((c) => c.method === 'POST' && c.path === '/api/doctors')).toBe(true))
    expect(calls.find((c) => c.method === 'POST')!.body).toMatchObject({ name: 'Dr. New', specialization: null })
  })
})

describe('more', () => {
  it('offers backup, export and sign out', async () => {
    mockApi(authed)
    renderApp('/more')
    expect(await screen.findByRole('link', { name: /full backup/i })).toHaveAttribute('href', '/api/backup')
    expect(screen.getByRole('link', { name: /export records/i })).toHaveAttribute('href', '/api/export/json')
    expect(screen.getByRole('button', { name: /sign out/i })).toBeInTheDocument()
    expect(screen.getByText(/naman@example\.com/)).toBeInTheDocument()
  })

  it('signs out', async () => {
    const calls = mockApi({ ...authed, 'POST /api/auth/logout': { ok: true } })
    renderApp('/more')
    await userEvent.click(await screen.findByRole('button', { name: /sign out/i }))
    expect(await screen.findByRole('link', { name: /sign in with google/i })).toBeInTheDocument()
    expect(calls.some((c) => c.method === 'POST' && c.path === '/api/auth/logout')).toBe(true)
  })
})
