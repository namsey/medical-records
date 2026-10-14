import { formatDate } from './format'
import { RECORD_TYPE_INFO } from './recordTypes'
import type { RecordFilters, RecordSummary } from './types'

const MONTHS_LONG = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December']

export interface MonthGroup {
  /** `YYYY-MM` */
  key: string
  /** e.g. "September 2026" */
  label: string
  records: RecordSummary[]
}

/** Group records under month/year headers, keeping the order they arrive in (newest or oldest first). */
export function groupByMonth(records: RecordSummary[]): MonthGroup[] {
  const groups: MonthGroup[] = []
  for (const record of records) {
    const key = record.record_date.slice(0, 7)
    let group = groups[groups.length - 1]
    if (!group || group.key !== key) {
      const [year = '', month = '1'] = key.split('-')
      group = { key, label: `${MONTHS_LONG[Number(month) - 1] ?? ''} ${year}`, records: [] }
      groups.push(group)
    }
    group.records.push(record)
  }
  return groups
}

/** "3 lab reports in 2026 tagged Blood" — the record count, worded to show which filters are on. */
export function describeCount(total: number, filters: RecordFilters): string {
  const [onlyType] = filters.types
  let noun = total === 1 ? 'record' : 'records'
  if (filters.types.length === 1 && onlyType) {
    noun =
      onlyType === 'other'
        ? `other ${noun}`
        : (total === 1 ? RECORD_TYPE_INFO[onlyType].label : RECORD_TYPE_INFO[onlyType].plural).toLowerCase()
  }
  const parts = [`${total} ${noun}`]
  if (filters.types.length > 1) parts.push(`of ${filters.types.length} types`)
  if (filters.year) parts.push(`in ${filters.year}`)
  if (filters.dateFrom && filters.dateTo) parts.push(`from ${formatDate(filters.dateFrom)} to ${formatDate(filters.dateTo)}`)
  else if (filters.dateFrom) parts.push(`from ${formatDate(filters.dateFrom)}`)
  else if (filters.dateTo) parts.push(`until ${formatDate(filters.dateTo)}`)
  if (filters.tags.length > 0) parts.push(`tagged ${filters.tags.join(', ')}`)
  if (filters.q.trim()) parts.push('found')
  return parts.join(' ')
}
