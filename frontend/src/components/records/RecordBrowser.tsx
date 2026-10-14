import { FolderOpen, FunnelX, Search, SearchX, X } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { useRecordFilters, countActiveFilters } from '@/hooks/useRecordFilters'
import { EMPTY_FILTERS, useRecordList } from '@/hooks/queries'
import { useDebounced } from '@/hooks/useDebounced'
import { errorMessage } from '@/lib/api'
import { describeCount, describeFilters, groupByMonth } from '@/lib/recordList'
import type { RecordSort } from '@/lib/types'
import { Button, LinkButton } from '../ui/Button'
import { CardSkeletons, EmptyState, ErrorMessage } from '../ui/feedback'
import { FilterPanel } from './FilterPanel'
import { QuickFilters } from './QuickFilters'
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
  const searching = withSearchBox && Boolean(filters.q.trim())
  const filtering = countActiveFilters(filters) > 0

  function clearSearch() {
    setText('')
    setFilters({ ...filters, q: '' })
    inputRef.current?.focus()
  }

  function clearFilters() {
    setFilters({ ...EMPTY_FILTERS, q: filters.q, sort: filters.sort })
  }

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

      {!withSearchBox && <QuickFilters filters={filters} onChange={setFilters} />}

      <FilterPanel filters={filters} onChange={setFilters} hideTypes={!withSearchBox} />

      {query.isPending && <CardSkeletons />}

      {query.isError && <ErrorMessage message={errorMessage(query.error)} onRetry={() => void query.refetch()} />}

      {query.isSuccess && records.length === 0 && (
        <>
          {searching ? (
            <EmptyState
              icon={SearchX}
              title={`No results for “${filters.q.trim()}”`}
              description={
                filtering
                  ? `Nothing matches with the filters on (${describeFilters(filters)}). Try clearing them, or search for something else.`
                  : 'Check the spelling, or search for a doctor, medicine, test, diagnosis or tag.'
              }
              action={
                <div className="flex flex-wrap justify-center gap-2">
                  <Button variant="secondary" onClick={clearSearch}>
                    Clear search
                  </Button>
                  {filtering && (
                    <Button variant="secondary" onClick={clearFilters}>
                      Clear filters
                    </Button>
                  )}
                </div>
              }
            />
          ) : filtering ? (
            <EmptyState
              icon={FunnelX}
              title="No records match these filters"
              description={`Nothing found for ${describeFilters(filters)}. Try another filter, or show everything.`}
              action={
                <Button variant="secondary" onClick={clearFilters}>
                  Clear filters
                </Button>
              }
            />
          ) : (
            <EmptyState
              icon={FolderOpen}
              title="No records yet"
              description="Add your first prescription, lab report or doctor visit, and it will show up here."
              action={<LinkButton to="/add">Add your first record</LinkButton>}
            />
          )}
        </>
      )}

      {records.length > 0 && (
        <>
          <div className="flex items-center justify-between gap-2 px-1">
            <p className="text-sm text-muted" aria-live="polite">
              {describeCount(total, withSearchBox ? filters : { ...filters, q: '' })}
            </p>
            {!withSearchBox && (
              <select
                aria-label="Sort records"
                value={filters.sort}
                onChange={(event) => setFilters({ ...filters, sort: event.target.value as RecordSort })}
                className="min-h-11 shrink-0 rounded-lg bg-transparent px-1 font-semibold text-ink hover:bg-wash"
              >
                <option value="newest">Newest first</option>
                <option value="oldest">Oldest first</option>
              </select>
            )}
          </div>
          {withSearchBox ? (
            <ul className="space-y-3">
              {records.map((record) => (
                <li key={record.id}>
                  <RecordCard record={record} />
                </li>
              ))}
            </ul>
          ) : (
            <div className="space-y-4">
              {groupByMonth(records).map((group) => (
                <section key={group.key} aria-labelledby={`month-${group.key}`} className="space-y-2">
                  <h2 id={`month-${group.key}`} className="px-1 font-sans text-sm font-semibold text-muted">
                    {group.label}
                  </h2>
                  <ul className="space-y-3">
                    {group.records.map((record) => (
                      <li key={record.id}>
                        <RecordCard record={record} />
                      </li>
                    ))}
                  </ul>
                </section>
              ))}
            </div>
          )}
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
