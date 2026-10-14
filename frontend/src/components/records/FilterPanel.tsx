import { ChevronDown, SlidersHorizontal } from 'lucide-react'
import { useState } from 'react'
import { useTags } from '@/hooks/queries'
import { RECORD_TYPES, RECORD_TYPE_INFO } from '@/lib/recordTypes'
import type { RecordFilters, RecordType } from '@/lib/types'
import { Button } from '../ui/Button'
import { ToggleChip } from '../ui/Chip'
import { Field } from '../ui/Field'

interface FilterPanelProps {
  filters: RecordFilters
  onChange: (next: RecordFilters) => void
  /** Timeline only filters by type. */
  typesOnly?: boolean
  /** Records picks the type with chips above the panel, so the panel leaves it out. */
  hideTypes?: boolean
}

function toggle<T>(list: T[], item: T): T[] {
  return list.includes(item) ? list.filter((entry) => entry !== item) : [...list, item]
}

export function FilterPanel({ filters, onChange, typesOnly = false, hideTypes = false }: FilterPanelProps) {
  const [open, setOpen] = useState(false)
  const { data: tags } = useTags()
  const panelFilters = typesOnly ? 0 : filters.tags.length + (filters.dateFrom ? 1 : 0) + (filters.dateTo ? 1 : 0)
  const active = (hideTypes ? 0 : filters.types.length) + panelFilters

  return (
    <div className="card">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        className="flex min-h-12 w-full items-center gap-2 px-4 text-left font-semibold"
      >
        <SlidersHorizontal className="size-5 text-brand-700" aria-hidden />
        Filters
        {active > 0 && <span className="rounded-full bg-brand-700 px-2 py-0.5 text-xs text-white">{active}</span>}
        <ChevronDown className={`ml-auto size-5 text-muted transition ${open ? 'rotate-180' : ''}`} aria-hidden />
      </button>

      {open && (
        <div className="space-y-5 border-t border-line p-4">
          {!hideTypes && (
            <Field label="Record type">
              <div className="flex flex-wrap gap-2">
                {RECORD_TYPES.map((type: RecordType) => (
                  <ToggleChip key={type} selected={filters.types.includes(type)} onClick={() => onChange({ ...filters, types: toggle(filters.types, type) })}>
                    {RECORD_TYPE_INFO[type].label}
                  </ToggleChip>
                ))}
              </div>
            </Field>
          )}

          {!typesOnly && (
            <>
              <div className="grid grid-cols-2 gap-3">
                <Field label="From" htmlFor="filter-from">
                  <input id="filter-from" type="date" className="field-input" value={filters.dateFrom} max={filters.dateTo || undefined} onChange={(event) => onChange({ ...filters, dateFrom: event.target.value })} />
                </Field>
                <Field label="To" htmlFor="filter-to">
                  <input id="filter-to" type="date" className="field-input" value={filters.dateTo} min={filters.dateFrom || undefined} onChange={(event) => onChange({ ...filters, dateTo: event.target.value })} />
                </Field>
              </div>

              {tags && tags.length > 0 && (
                <Field label="Tags" hint="Records must have every selected tag.">
                  <div className="flex flex-wrap gap-2">
                    {tags.map((tag) => (
                      <ToggleChip
                        key={tag.name}
                        selected={filters.tags.some((selected) => selected.toLowerCase() === tag.name.toLowerCase())}
                        onClick={() => onChange({ ...filters, tags: toggle(filters.tags, tag.name) })}
                      >
                        {tag.name}
                      </ToggleChip>
                    ))}
                  </div>
                </Field>
              )}
            </>
          )}

          {active > 0 && (
            <Button variant="ghost" size="sm" onClick={() => onChange({ ...filters, types: hideTypes ? filters.types : [], tags: typesOnly ? filters.tags : [], dateFrom: typesOnly ? filters.dateFrom : '', dateTo: typesOnly ? filters.dateTo : '' })}>
              Clear filters
            </Button>
          )}
        </div>
      )}
    </div>
  )
}
