import { useParams } from 'react-router-dom'
import { PageHeader } from '@/components/layout/PageHeader'
import { RecordForm } from '@/components/records/RecordForm'
import { ErrorMessage, LoadingState } from '@/components/ui/feedback'
import { useRecord } from '@/hooks/queries'
import { ApiError, errorMessage } from '@/lib/api'
import { formFromRecord } from '@/lib/recordForm'

export function EditRecordPage() {
  const { id } = useParams()
  const { data: record, isPending, error, refetch } = useRecord(id)

  if (isPending) return <LoadingState />
  if (error || !record) {
    const missing = error instanceof ApiError && error.status === 404
    return (
      <>
        <PageHeader title="Edit record" back="/records" />
        <ErrorMessage message={missing ? 'This record no longer exists.' : errorMessage(error)} onRetry={missing ? undefined : () => void refetch()} />
      </>
    )
  }

  return (
    // Keyed so the form starts from the freshly loaded record; later background refetches never overwrite typing.
    <RecordForm key={record.id} title="Edit record" initial={formFromRecord(record)} existing={record} />
  )
}
