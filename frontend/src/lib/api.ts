/** Thin fetch wrapper for the backend API. Cookies carry the login session. */

export class ApiError extends Error {
  readonly status: number

  constructor(status: number, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

// Required by the backend on every state-changing request (CSRF protection).
const CSRF_HEADERS = { 'X-Requested-With': 'XMLHttpRequest' }

interface ValidationIssue {
  loc?: unknown[]
  msg?: string
}

function describeIssue(issue: ValidationIssue): string {
  const field = (issue.loc ?? []).filter((part) => part !== 'body' && typeof part === 'string').join(' › ')
  const message = (issue.msg ?? 'Invalid value').replace(/^Value error, /, '')
  return field ? `${field.replace(/_/g, ' ')}: ${message}` : message
}

async function errorFromResponse(response: Response): Promise<ApiError> {
  let message = `Request failed (${response.status})`
  try {
    const body: unknown = await response.json()
    const detail = (body as { detail?: unknown }).detail
    if (typeof detail === 'string') message = detail
    else if (Array.isArray(detail)) message = detail.map((issue) => describeIssue(issue as ValidationIssue)).join('\n')
  } catch {
    if (response.status === 413) message = 'The file is too large.'
  }
  return new ApiError(response.status, message)
}

interface RequestOptions {
  method?: 'GET' | 'POST' | 'PUT' | 'DELETE'
  json?: unknown
  form?: FormData
  signal?: AbortSignal
}

export async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = 'GET', json, form, signal } = options
  const headers: Record<string, string> = { ...CSRF_HEADERS }
  let body: BodyInit | undefined
  if (json !== undefined) {
    headers['Content-Type'] = 'application/json'
    body = JSON.stringify(json)
  } else if (form) {
    body = form
  }

  let response: Response
  try {
    response = await fetch(path, { method, headers, body, signal, credentials: 'same-origin' })
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw error
    throw new ApiError(0, 'Could not reach the server. Check your connection and try again.')
  }
  if (!response.ok) throw await errorFromResponse(response)
  if (response.status === 204) return undefined as T
  return (await response.json()) as T
}

/** Fetch a protected file as bytes (used by the PDF viewer). */
export async function fetchBytes(path: string, signal?: AbortSignal): Promise<ArrayBuffer> {
  let response: Response
  try {
    response = await fetch(path, { credentials: 'same-origin', signal })
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw error
    throw new ApiError(0, 'Could not reach the server. Check your connection and try again.')
  }
  if (!response.ok) throw await errorFromResponse(response)
  return response.arrayBuffer()
}

export const documentUrls = {
  view: (id: string) => `/api/documents/${id}/view`,
  download: (id: string) => `/api/documents/${id}/download`,
}

export function errorMessage(error: unknown): string {
  if (error instanceof Error) return error.message
  return 'Something went wrong. Please try again.'
}
