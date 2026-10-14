import { CalendarClock, Paperclip } from 'lucide-react'
import { useMemo } from 'react'
import { Link } from 'react-router-dom'
import { PageHeader } from '@/components/layout/PageHeader'
import { FilterPanel } from '@/components/records/FilterPanel'
import { TypeIcon } from '@/components/records/RecordCard'
import { ViewSwitch } from '@/components/records/ViewSwitch'
import { LinkButton } from '@/components/ui/Button'
import { CardSkeletons, EmptyState, ErrorMessage } from '@/components/ui/feedback'
import { useTimeline } from '@/hooks/queries'
import { useRecordFilters } from '@/hooks/useRecordFilters'
import { errorMessage } from '@/lib/api'
import { formatDayMonth, yearOf } from '@/lib/format'
import { RECORD_TYPE_INFO } from '@/lib/recordTypes'
import type { TimelineItem } from '@/lib/types'

interface DayGroup {
  date: string
  items: TimelineItem[]
}
interface YearGroup {
  year: string
  days: DayGroup[]
}

/** The API returns records newest first; group them by year, then by day, keeping that order. */
function groupByYearAndDay(items: TimelineItem[]): YearGroup[] {
  const years: YearGroup[] = []
  for (const item of items) {
    const year = yearOf(item.record_date)
    let yearGroup = years[years.length - 1]
    if (!yearGroup || yearGroup.year !== year) {
      yearGroup = { year, days: [] }
      years.push(yearGroup)
    }
    let day = yearGroup.days[yearGroup.days.length - 1]
    if (!day || day.date !== item.record_date) {
      day = { date: item.record_date, items: [] }
      yearGroup.days.push(day)
    }
    day.items.push(item)
  }
  return years
}

export function TimelinePage() {
  const [filters, setFilters] = useRecordFilters()
  const { data, isPending, isError, error, refetch } = useTimeline(filters.types)
  const groups = useMemo(() => groupByYearAndDay(data ?? []), [data])

  return (
    <>
      <PageHeader title="Records" />
      <ViewSwitch active="timeline" />
      <div className="mb-5">
        <FilterPanel filters={filters} onChange={setFilters} typesOnly />
      </div>

      {isPending && <CardSkeletons />}
      {isError && <ErrorMessage message={errorMessage(error)} onRetry={() => void refetch()} />}
      {data && data.length === 0 && (
        <EmptyState
          icon={CalendarClock}
          title="Nothing on the timeline"
          description={filters.types.length ? 'No records of the selected types.' : 'Records you add will appear here in date order.'}
          action={filters.types.length ? undefined : <LinkButton to="/add">Add a record</LinkButton>}
        />
      )}

      <div className="space-y-8">
        {groups.map((group) => (
          <section key={group.year} aria-label={group.year}>
            <h2 className="section-heading mb-3">{group.year}</h2>
            <ol className="space-y-5 border-l-2 border-line pl-4">
              {group.days.map((day) => (
                <li key={day.date} className="relative">
                  <span className="absolute -left-[1.4rem] top-1.5 size-3 rounded-full border-2 border-paper bg-brand-600" aria-hidden />
                  <h3 className="group-heading mb-2">{formatDayMonth(day.date)}</h3>
                  <ul className="space-y-2">
                    {day.items.map((item) => (
                      <li key={item.id}>
                        <Link to={`/records/${item.id}`} className="card flex items-center gap-3 p-3 transition active:bg-wash">
                          <TypeIcon type={item.record_type} className="size-10" />
                          <div className="min-w-0 flex-1">
                            <p className="truncate font-semibold leading-snug">{item.title}</p>
                            <p className="truncate text-sm text-muted">
                              {[RECORD_TYPE_INFO[item.record_type].label, item.doctor_name, item.lab_name].filter(Boolean).join(' · ')}
                            </p>
                          </div>
                          {item.document_count > 0 && <Paperclip className="size-4 shrink-0 text-muted" aria-label="Has attachments" />}
                        </Link>
                      </li>
                    ))}
                  </ul>
                </li>
              ))}
            </ol>
          </section>
        ))}
      </div>
    </>
  )
}
