import { ChevronRight } from 'lucide-react'
import { Fragment } from 'react'
import { Link } from 'react-router-dom'
import { formatDate, pluralize } from '@/lib/format'
import { RECORD_TYPE_INFO } from '@/lib/recordTypes'
import type { RecordSummary, RecordType, TimelineItem } from '@/lib/types'
import { TagPill } from '../ui/Chip'

export function TypeIcon({ type, className = 'size-11' }: { type: RecordType; className?: string }) {
  const { icon: Icon, tone } = RECORD_TYPE_INFO[type]
  return (
    <span className={`grid shrink-0 place-items-center rounded-xl ${tone} ${className}`}>
      <Icon className="size-5" aria-hidden />
    </span>
  )
}

export function TypeBadge({ type }: { type: RecordType }) {
  const { label, tone, icon: Icon } = RECORD_TYPE_INFO[type]
  return (
    <span className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-semibold ${tone}`}>
      <Icon className="size-3.5" aria-hidden />
      {label}
    </span>
  )
}

const MAX_TAGS_SHOWN = 3

/** The one record card, used by every list (timeline items carry no hospital or tags). */
export function RecordCard({ record }: { record: RecordSummary | TimelineItem }) {
  const hospital = 'hospital' in record ? record.hospital : null
  const tags = 'tags' in record ? record.tags : []
  const who = [record.doctor_name, record.lab_name, hospital].filter(Boolean)
  const extraTags = tags.length - MAX_TAGS_SHOWN
  const meta = [RECORD_TYPE_INFO[record.record_type].label, formatDate(record.record_date)]
  if (record.document_count > 0) meta.push(pluralize(record.document_count, 'file'))
  return (
    <Link to={`/records/${record.id}`} className="card flex items-center gap-3 p-4 transition active:bg-wash">
      <TypeIcon type={record.record_type} />
      <div className="min-w-0 flex-1">
        <p className="truncate font-semibold leading-snug">{record.title}</p>
        {/* Each part stays whole; on narrow screens the line only wraps between parts. */}
        <p className="text-sm text-muted">
          {meta.map((part, index) => (
            <Fragment key={part}>
              {index > 0 && ' · '}
              <span className="whitespace-nowrap">{part}</span>
            </Fragment>
          ))}
        </p>
        {who.length > 0 && <p className="truncate text-sm text-muted">{who.join(' · ')}</p>}
        {tags.length > 0 && (
          <div className="mt-1.5 flex flex-wrap gap-1.5">
            {tags.slice(0, MAX_TAGS_SHOWN).map((tag) => (
              <TagPill key={tag}>{tag}</TagPill>
            ))}
            {extraTags > 0 && <span className="py-1 text-xs text-muted">+{extraTags}</span>}
          </div>
        )}
      </div>
      <ChevronRight className="size-5 shrink-0 text-muted" aria-hidden />
    </Link>
  )
}
