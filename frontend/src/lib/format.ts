const MONTHS_SHORT = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

/** Parse a `YYYY-MM-DD` string as a local calendar date (avoids timezone shifts). */
function parseDate(value: string): { year: number; month: number; day: number } {
  const [year = 0, month = 1, day = 1] = value.slice(0, 10).split('-').map(Number)
  return { year, month, day }
}

/** 05 Sep 2026 */
export function formatDate(value: string | null | undefined): string {
  if (!value) return ''
  const { year, month, day } = parseDate(value)
  return `${String(day).padStart(2, '0')} ${MONTHS_SHORT[month - 1] ?? ''} ${year}`
}

/** 05 Sep */
export function formatDayMonth(value: string): string {
  const { month, day } = parseDate(value)
  return `${String(day).padStart(2, '0')} ${MONTHS_SHORT[month - 1] ?? ''}`
}

export function yearOf(value: string): string {
  return value.slice(0, 4)
}

/** Today as YYYY-MM-DD in the user's local time zone. */
export function todayIso(): string {
  const now = new Date()
  const month = String(now.getMonth() + 1).padStart(2, '0')
  const day = String(now.getDate()).padStart(2, '0')
  return `${now.getFullYear()}-${month}-${day}`
}

export function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

/** Empty / whitespace-only strings become null, as the API expects. */
export function orNull(value: string): string | null {
  const trimmed = value.trim()
  return trimmed === '' ? null : trimmed
}

export function pluralize(count: number, singular: string, plural = `${singular}s`): string {
  return `${count} ${count === 1 ? singular : plural}`
}
