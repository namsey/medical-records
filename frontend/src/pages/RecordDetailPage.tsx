import { Pencil, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { DocumentList } from '@/components/documents/DocumentList'
import { FilePicker } from '@/components/documents/FilePicker'
import { PageHeader } from '@/components/layout/PageHeader'
import { MedicineList, RecordFacts, ResultList, TagLinks } from '@/components/records/RecordDetails'
import { TypeBadge } from '@/components/records/RecordCard'
import { Button } from '@/components/ui/Button'
import { ErrorMessage, LoadingState } from '@/components/ui/feedback'
import { ConfirmDialog } from '@/components/ui/Modal'
import { useToast } from '@/components/ui/Toast'
import { useDeleteRecord, useRecord, useUploadDocuments } from '@/hooks/queries'
import { ApiError, errorMessage } from '@/lib/api'
import { formatDate } from '@/lib/format'

export function RecordDetailPage() {
  const { id } = useParams()
  const { data: record, isPending, error, refetch } = useRecord(id)
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [newFiles, setNewFiles] = useState<File[]>([])
  const remove = useDeleteRecord()
  const upload = useUploadDocuments(id ?? '')
  const navigate = useNavigate()
  const toast = useToast()

  if (isPending) return <LoadingState />
  if (error || !record) {
    const missing = error instanceof ApiError && error.status === 404
    return (
      <>
        <PageHeader title="Record" back="/records" />
        <ErrorMessage message={missing ? 'This record no longer exists.' : errorMessage(error)} onRetry={missing ? undefined : () => void refetch()} />
      </>
    )
  }

  const who = [record.doctor?.name, record.lab?.name].filter(Boolean).join(' · ')

  return (
    <div className="space-y-5">
      <PageHeader
        title={record.title}
        back
        action={
          <Link to={`/records/${record.id}/edit`} aria-label="Edit record" className="grid size-11 place-items-center rounded-full text-brand-700 hover:bg-brand-50">
            <Pencil className="size-5" />
          </Link>
        }
      />

      <div className="flex flex-wrap items-center gap-2 text-sm text-muted">
        <TypeBadge type={record.record_type} />
        <span>{formatDate(record.record_date)}</span>
        {who && <span>· {who}</span>}
      </div>

      <TagLinks tags={record.tags} />
      <RecordFacts record={record} />
      <MedicineList medicines={record.medicines} />
      <ResultList results={record.results} />

      {record.personal_notes && (
        <section className="space-y-2">
          <h2 className="section-heading">Personal notes</h2>
          <p className="card whitespace-pre-line break-words bg-wash p-4 leading-relaxed">{record.personal_notes}</p>
        </section>
      )}

      <section className="space-y-3">
        <h2 className="section-heading">Attachments</h2>
        {record.documents.length === 0 && <p className="text-sm text-muted">No files attached.</p>}
        <DocumentList documents={record.documents} />
        <FilePicker label="Add files" files={newFiles} onChange={setNewFiles} disabled={upload.isPending} />
        {newFiles.length > 0 && (
          <Button
            className="w-full"
            loading={upload.isPending}
            onClick={() =>
              upload.mutate(newFiles, {
                onSuccess: () => {
                  setNewFiles([])
                  toast.success('Files uploaded')
                },
                onError: (uploadError) => {
                  setNewFiles([])
                  toast.error(`Some files were not uploaded:\n${uploadError.message}`)
                },
              })
            }
          >
            Upload {newFiles.length} {newFiles.length === 1 ? 'file' : 'files'}
          </Button>
        )}
      </section>

      <Button variant="dangerOutline" className="w-full" onClick={() => setConfirmDelete(true)}>
        <Trash2 className="size-5" aria-hidden />
        Delete record
      </Button>

      <ConfirmDialog
        open={confirmDelete}
        title="Delete this record?"
        message="The record and all of its attached files will be permanently deleted. This cannot be undone."
        loading={remove.isPending}
        error={remove.isError ? errorMessage(remove.error) : null}
        onCancel={() => {
          setConfirmDelete(false)
          remove.reset()
        }}
        onConfirm={() =>
          remove.mutate(record.id, {
            onSuccess: () => {
              toast.success('Record deleted')
              navigate('/records', { replace: true })
            },
          })
        }
      />
    </div>
  )
}
