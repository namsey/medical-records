import { useCallback, useMemo } from 'react'
import { useSearchParams } from 'react-router-dom'
import { RECORD_TYPES } from '@/lib/recordTypes'
import type { RecordFilters, RecordType } from '@/lib/types'

function isRecordType(value: string): value is RecordType {
  return (RECORD_TYPES as string[]).includes(value)
}

/** Filters live in the URL, so back-navigation and reloads keep the user's place. */
export function useRecordFilters(): [RecordFilters, (next: RecordFilters) => void] {
  const [params, setParams] = useSearchParams()

  const filters = useMemo<RecordFilters>(
    () => ({
      q: params.get('q') ?? '',
      types: params.getAll('type').filter(isRecordType),
      tags: params.getAll('tag'),
      dateFrom: params.get('from') ?? '',
      dateTo: params.get('to') ?? '',
    }),
    [params],
  )

  const setFilters = useCallback(
    (next: RecordFilters) => {
      const updated = new URLSearchParams()
      if (next.q.trim()) updated.set('q', next.q)
      next.types.forEach((type) => updated.append('type', type))
      next.tags.forEach((tag) => updated.append('tag', tag))
      if (next.dateFrom) updated.set('from', next.dateFrom)
      if (next.dateTo) updated.set('to', next.dateTo)
      setParams(updated, { replace: true })
    },
    [setParams],
  )

  return [filters, setFilters]
}

export function countActiveFilters(filters: RecordFilters): number {
  return filters.types.length + filters.tags.length + (filters.dateFrom ? 1 : 0) + (filters.dateTo ? 1 : 0)
}
