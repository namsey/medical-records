import { useEffect, useRef } from 'react'
import { useYears } from '@/hooks/queries'
import { RECORD_TYPES, RECORD_TYPE_INFO } from '@/lib/recordTypes'
import type { RecordFilters } from '@/lib/types'
import { ToggleChip } from '../ui/Chip'

interface QuickFiltersProps {
  filters: RecordFilters
  onChange: (next: RecordFilters) => void
}

/** One horizontally scrolling row of chips: All, each record type, then each year that has records. */
export function QuickFilters({ filters, onChange }: QuickFiltersProps) {
  const { data: years } = useYears()
  const all = filters.types.length === 0 && !filters.year
  const onlyType = filters.types.length === 1 ? filters.types[0] : undefined
  const rowRef = useRef<HTMLDivElement>(null)

  // Keep the last selected chip in view, e.g. a year chip at the far end when the page opens with it selected.
  const yearsLoaded = Boolean(years)
  useEffect(() => {
    const row = rowRef.current
    const selected = row?.querySelectorAll<HTMLElement>('[aria-pressed="true"]')
    const last = selected?.[selected.length - 1]
    if (row && last && (last.offsetLeft < row.scrollLeft || last.offsetLeft + last.offsetWidth > row.scrollLeft + row.clientWidth)) {
      row.scrollTo({ left: last.offsetLeft - 16 })
    }
  }, [yearsLoaded])

  return (
    <div ref={rowRef} role="group" aria-label="Quick filters" className="relative -mx-4 overflow-x-auto px-4 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
      <ul className="flex w-max items-center gap-2 py-0.5">
        <li>
          <ToggleChip selected={all} onClick={() => onChange({ ...filters, types: [], year: '' })}>
            All
          </ToggleChip>
        </li>
        {RECORD_TYPES.map((type) => (
          <li key={type}>
            <ToggleChip selected={filters.types.includes(type)} onClick={() => onChange({ ...filters, types: onlyType === type ? [] : [type] })}>
              {RECORD_TYPE_INFO[type].label}
            </ToggleChip>
          </li>
        ))}
        {years && years.length > 0 && <li aria-hidden className="mx-1 h-6 w-px bg-line" />}
        {years?.map(({ year }) => (
          <li key={year}>
            <ToggleChip selected={filters.year === String(year)} onClick={() => onChange({ ...filters, year: filters.year === String(year) ? '' : String(year) })}>
              {year}
            </ToggleChip>
          </li>
        ))}
      </ul>
    </div>
  )
}
