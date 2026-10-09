import { ChevronRight, Paperclip } from 'lucide-react'
import { Link } from 'react-router-dom'
import { formatDate } from '@/lib/format'
import { RECORD_TYPE_INFO } from '@/lib/recordTypes'
import type { RecordSummary, RecordType } from '@/lib/types'
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

export function RecordCard({ record }: { record: RecordSummary }) {
  const who = [record.doctor_name, record.lab_name, record.hospital].filter(Boolean)
  const extraTags = record.tags.length - MAX_TAGS_SHOWN
  return (
    <Link to={`/records/${record.id}`} className="card flex items-center gap-3 p-4 transition active:bg-wash">
      <TypeIcon type={record.record_type} />
      <div className="min-w-0 flex-1">
        <p className="truncate font-semibold leading-snug">{record.title}</p>
        <p className="truncate text-sm text-muted">
          {RECORD_TYPE_INFO[record.record_type].label} · {formatDate(record.record_date)}
        </p>
        {who.length > 0 && <p className="truncate text-sm text-muted">{who.join(' · ')}</p>}
        {record.tags.length > 0 && (
          <div className="mt-1.5 flex flex-wrap gap-1.5">
            {record.tags.slice(0, MAX_TAGS_SHOWN).map((tag) => (
              <TagPill key={tag}>{tag}</TagPill>
            ))}
            {extraTags > 0 && <span className="py-1 text-xs text-muted">+{extraTags}</span>}
          </div>
        )}
      </div>
      <div className="flex shrink-0 flex-col items-end gap-2 text-muted">
        {record.document_count > 0 && (
          <span className="inline-flex items-center gap-1 text-xs font-medium" aria-label={`${record.document_count} attachments`}>
            <Paperclip className="size-4" aria-hidden />
            {record.document_count}
          </span>
        )}
        <ChevronRight className="size-5" aria-hidden />
      </div>
    </Link>
  )
}
