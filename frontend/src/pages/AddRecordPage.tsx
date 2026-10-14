import { ChevronRight } from 'lucide-react'
import { Link, Navigate, useParams } from 'react-router-dom'
import { PageHeader } from '@/components/layout/PageHeader'
import { useGoBack } from '@/hooks/useGoBack'
import { RecordForm } from '@/components/records/RecordForm'
import { TypeIcon } from '@/components/records/RecordCard'
import { emptyForm } from '@/lib/recordForm'
import { RECORD_TYPES, RECORD_TYPE_INFO } from '@/lib/recordTypes'
import type { RecordType } from '@/lib/types'

function isRecordType(value: string | undefined): value is RecordType {
  return value !== undefined && (RECORD_TYPES as string[]).includes(value)
}

export function AddRecordPage() {
  const { type } = useParams()
  const goBack = useGoBack('/')

  if (type === undefined) {
    return (
      <>
        <PageHeader title="Add record" subtitle="What would you like to add?" onBack={goBack} backIcon="close" />
        <ul className="space-y-3">
          {RECORD_TYPES.map((recordType) => {
            const info = RECORD_TYPE_INFO[recordType]
            return (
              <li key={recordType}>
                <Link to={`/add/${recordType}`} className="card flex min-h-[4.5rem] items-center gap-4 p-4 transition active:bg-wash">
                  <TypeIcon type={recordType} className="size-12" />
                  <div className="min-w-0 flex-1">
                    <p className="text-lg font-semibold leading-snug">{info.label}</p>
                    <p className="text-sm text-muted">{info.hint}</p>
                  </div>
                  <ChevronRight className="size-5 text-muted" aria-hidden />
                </Link>
              </li>
            )
          })}
        </ul>
      </>
    )
  }

  if (!isRecordType(type)) return <Navigate to="/add" replace />

  return <RecordForm key={type} title={`New ${RECORD_TYPE_INFO[type].label.toLowerCase()}`} initial={emptyForm(type)} />
}
