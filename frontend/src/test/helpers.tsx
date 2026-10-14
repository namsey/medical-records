import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render } from '@testing-library/react'
import { createMemoryRouter, RouterProvider } from 'react-router-dom'
import { vi } from 'vitest'
import { App } from '@/App'
import { ToastProvider } from '@/components/ui/Toast'
import { ApiError } from '@/lib/api'
import { MutationCache, QueryCache } from '@tanstack/react-query'
import { ME_KEY } from '@/lib/queryClient'
import type { MedicalRecord, RecordSummary } from '@/lib/types'

export interface RecordedCall {
  method: string
  path: string
  params: URLSearchParams
  body: unknown
  headers: Record<string, string>
}

type Handler = (call: RecordedCall) => { status?: number; json?: unknown } | undefined

/**
 * Replaces fetch with an in-memory fake of the API. Routes are keyed "METHOD /path" (query string ignored).
 * Returns the list of calls made, so tests can assert on what the app sent.
 */
type Route = Handler | object

export function mockApi(routes: Record<string, Route>): RecordedCall[] {
  const calls: RecordedCall[] = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = new URL(String(input), 'http://localhost')
      const method = (init?.method ?? 'GET').toUpperCase()
      let body: unknown = init?.body
      if (typeof body === 'string') body = JSON.parse(body)
      const call: RecordedCall = { method, path: url.pathname, params: url.searchParams, body, headers: (init?.headers ?? {}) as Record<string, string> }
      calls.push(call)
      const route = routes[`${method} ${url.pathname}`]
      if (route === undefined) return new Response(JSON.stringify({ detail: `No mock for ${method} ${url.pathname}` }), { status: 404 })
      const result = typeof route === 'function' ? route(call) : { json: route }
      const status = result?.status ?? 200
      if (status === 204) return new Response(null, { status })
      return new Response(JSON.stringify(result?.json ?? {}), { status, headers: { 'Content-Type': 'application/json' } })
    }),
  )
  return calls
}

export function renderApp(path = '/') {
  const queryClient: QueryClient = new QueryClient({
    queryCache: new QueryCache({
      onError: (error) => {
        if (error instanceof ApiError && error.status === 401) queryClient.setQueryData(ME_KEY, null)
      },
    }),
    mutationCache: new MutationCache(),
    defaultOptions: { queries: { retry: false, staleTime: 0 } },
  })
  // Same shape as main.tsx: a data router with one catch-all route around the app's own <Routes>.
  const router = createMemoryRouter(
    [
      {
        path: '*',
        element: (
          <ToastProvider>
            <App />
          </ToastProvider>
        ),
      },
    ],
    { initialEntries: [path] },
  )
  return render(
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  )
}

export const USER = { email: 'naman@example.com', name: 'Naman' }

export function summary(overrides: Partial<RecordSummary> = {}): RecordSummary {
  return {
    id: 'r1',
    record_type: 'lab_report',
    title: 'Lab Report - Vitamin B12',
    record_date: '2026-09-10',
    doctor_name: 'Dr. Anita Sharma',
    lab_name: 'Pathcare Diagnostics',
    hospital: null,
    tags: ['Blood', 'B12'],
    document_count: 1,
    ...overrides,
  }
}

export function fullRecord(overrides: Partial<MedicalRecord> = {}): MedicalRecord {
  return {
    id: 'r1',
    record_type: 'lab_report',
    title: 'Lab Report - Vitamin B12',
    record_date: '2026-09-10',
    doctor_id: null,
    lab_id: null,
    doctor: null,
    lab: null,
    hospital: null,
    specialization: null,
    reason: null,
    symptoms: null,
    diagnosis: null,
    description: null,
    treatment: null,
    doctor_notes: null,
    summary: 'Within range',
    personal_notes: 'Felt tired that week',
    test_name: 'Vitamin B12',
    follow_up_date: null,
    report_date: '2026-09-11',
    tags: ['Blood'],
    medicines: [],
    results: [{ id: 'x1', parameter: 'Vitamin B12', value: '296', unit: 'pg/mL', reference_range: '200-900', flag: 'Normal' }],
    documents: [{ id: 'd1', record_id: 'r1', original_filename: 'b12.pdf', content_type: 'application/pdf', size_bytes: 2048, created_at: '2026-09-10T10:00:00Z' }],
    created_at: '2026-09-10T10:00:00Z',
    updated_at: '2026-09-10T10:00:00Z',
    ...overrides,
  }
}
