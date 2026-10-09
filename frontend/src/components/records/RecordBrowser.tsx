import { FileSearch, FolderOpen, Search, X } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { useRecordFilters, countActiveFilters } from '@/hooks/useRecordFilters'
import { useRecordList } from '@/hooks/queries'
import { useDebounced } from '@/hooks/useDebounced'
import { errorMessage } from '@/lib/api'
import { pluralize } from '@/lib/format'
import { Button, LinkButton } from '../ui/Button'
import { CardSkeletons, EmptyState, ErrorMessage } from '../ui/feedback'
import { FilterPanel } from './FilterPanel'
import { RecordCard } from './RecordCard'

interface RecordBrowserProps {
  /** Show the free-text search box (the Search tab) or just the filters (the Records tab). */
  withSearchBox: boolean
}

export function RecordBrowser({ withSearchBox }: RecordBrowserProps) {
  const [filters, setFilters] = useRecordFilters()
  const [text, setText] = useState(filters.q)
  const debouncedText = useDebounced(text, 300)
  const inputRef = useRef<HTMLInputElement>(null)

  // Push the debounced search text into the URL (and therefore into the query).
  const filtersRef = useRef(filters)
  filtersRef.current = filters
  useEffect(() => {
    if (withSearchBox && debouncedText !== filtersRef.current.q) {
      setFilters({ ...filtersRef.current, q: debouncedText })
    }
  }, [debouncedText, withSearchBox, setFilters])

  useEffect(() => {
    if (withSearchBox) inputRef.current?.focus()
  }, [withSearchBox])

  const query = useRecordList(withSearchBox ? filters : { ...filters, q: '' })
  const records = query.data?.pages.flatMap((page) => page.items) ?? []
  const total = query.data?.pages[0]?.total ?? 0
  const hasCriteria = Boolean(filters.q.trim()) || countActiveFilters(filters) > 0

  return (
    <div className="space-y-3">
      {withSearchBox && (
        <form
          role="search"
          onSubmit={(event) => {
            event.preventDefault()
            inputRef.current?.blur()
          }}
          className="relative"
        >
          <Search className="pointer-events-none absolute left-3.5 top-1/2 size-5 -translate-y-1/2 text-muted" aria-hidden />
          <input
            ref={inputRef}
            type="search"
            enterKeyHint="search"
            value={text}
            onChange={(event) => setText(event.target.value)}
            placeholder="Doctor, medicine, test, diagnosis, tag…"
            aria-label="Search records"
            maxLength={200}
            className="field-input min-h-14 rounded-2xl pl-11 pr-11"
          />
          {text && (
            <button
              type="button"
              onClick={() => {
                setText('')
                inputRef.current?.focus()
              }}
              aria-label="Clear search"
              className="absolute right-1.5 top-1/2 grid size-11 -translate-y-1/2 place-items-center rounded-full text-muted hover:bg-wash"
            >
              <X className="size-5" />
            </button>
          )}
        </form>
      )}

      <FilterPanel filters={filters} onChange={setFilters} />

      {query.isPending && <CardSkeletons />}

      {query.isError && <ErrorMessage message={errorMessage(query.error)} onRetry={() => void query.refetch()} />}

      {query.isSuccess && records.length === 0 && (
        <>
          {hasCriteria ? (
            <EmptyState
              icon={FileSearch}
              title="No matching records"
              description="Try different words or clear some filters."
              action={
                <Button variant="secondary" onClick={() => { setText(''); setFilters({ q: '', types: [], tags: [], dateFrom: '', dateTo: '' }) }}>
                  Clear search and filters
                </Button>
              }
            />
          ) : (
            <EmptyState
              icon={FolderOpen}
              title="No records yet"
              description="Add your first prescription, lab report or doctor visit."
              action={<LinkButton to="/add">Add a record</LinkButton>}
            />
          )}
        </>
      )}

      {records.length > 0 && (
        <>
          <p className="px-1 text-sm text-muted" aria-live="polite">
            {pluralize(total, 'record')}
            {hasCriteria ? ' found' : ''}
          </p>
          <ul className="space-y-3">
            {records.map((record) => (
              <li key={record.id}>
                <RecordCard record={record} />
              </li>
            ))}
          </ul>
          {query.hasNextPage && (
            <Button variant="secondary" className="w-full" loading={query.isFetchingNextPage} onClick={() => void query.fetchNextPage()}>
              Load more
            </Button>
          )}
        </>
      )}
    </div>
  )
}
