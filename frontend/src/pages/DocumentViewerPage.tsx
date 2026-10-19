import { Download, Minus, Plus, Trash2 } from 'lucide-react'
import { lazy, Suspense, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { isPdf } from '@/components/documents/DocumentList'
import { PageHeader } from '@/components/layout/PageHeader'
import { buttonClasses } from '@/components/ui/Button'
import { ErrorMessage, LoadingState } from '@/components/ui/feedback'
import { ConfirmDialog } from '@/components/ui/Modal'
import { useToast } from '@/components/ui/Toast'
import { ImageViewer } from '@/components/viewer/ImageViewer'
import { useDeleteDocument, useDocument } from '@/hooks/queries'
import { ApiError, documentUrls, errorMessage } from '@/lib/api'
import { formatFileSize } from '@/lib/format'

// pdf.js is large, so it is only downloaded when a PDF is actually opened.
const PdfViewer = lazy(() => import('@/components/viewer/PdfViewer').then((module) => ({ default: module.PdfViewer })))

const ZOOM_STEPS = [0.5, 0.75, 1, 1.25, 1.5, 2, 3]

export function DocumentViewerPage() {
  const { id } = useParams()
  const { data: document, isPending, error, refetch } = useDocument(id)
  const [zoomIndex, setZoomIndex] = useState(2)
  const [confirmDelete, setConfirmDelete] = useState(false)
  const remove = useDeleteDocument()
  const navigate = useNavigate()
  const toast = useToast()

  if (isPending) return <LoadingState />
  if (error || !document) {
    const missing = error instanceof ApiError && error.status === 404
    return (
      <>
        <PageHeader title="File" back />
        <ErrorMessage message={missing ? 'This file no longer exists.' : errorMessage(error)} onRetry={missing ? undefined : () => void refetch()} />
      </>
    )
  }

  const zoom = ZOOM_STEPS[zoomIndex] ?? 1
  const recordPath = `/records/${document.record_id}`

  return (
    <div className="space-y-3">
      <PageHeader
        title={document.original_filename}
        subtitle={`${isPdf(document) ? 'PDF' : 'Image'} · ${formatFileSize(document.size_bytes)}`}
        back={recordPath}
        action={
          <a href={documentUrls.download(document.id)} download={document.original_filename} aria-label="Download" className="grid size-11 place-items-center rounded-full text-brand-700 hover:bg-brand-50">
            <Download className="size-5" />
          </a>
        }
      />

      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-1" role="group" aria-label="Zoom">
          <button type="button" onClick={() => setZoomIndex((i) => Math.max(0, i - 1))} disabled={zoomIndex === 0} aria-label="Zoom out" className={buttonClasses('secondary', 'sm', 'w-11 px-0')}>
            <Minus className="size-5" />
          </button>
          <button type="button" onClick={() => setZoomIndex(2)} aria-label="Reset zoom" className={buttonClasses('secondary', 'sm', 'min-w-16')}>
            {Math.round(zoom * 100)}%
          </button>
          <button type="button" onClick={() => setZoomIndex((i) => Math.min(ZOOM_STEPS.length - 1, i + 1))} disabled={zoomIndex === ZOOM_STEPS.length - 1} aria-label="Zoom in" className={buttonClasses('secondary', 'sm', 'w-11 px-0')}>
            <Plus className="size-5" />
          </button>
        </div>
        <button type="button" onClick={() => setConfirmDelete(true)} className={buttonClasses('dangerOutline', 'sm')}>
          <Trash2 className="size-4" aria-hidden />
          Delete
        </button>
      </div>

      {isPdf(document) ? (
        <Suspense fallback={<LoadingState label="Opening PDF…" />}>
          <PdfViewer url={documentUrls.view(document.id)} zoom={zoom} />
        </Suspense>
      ) : (
        <ImageViewer
          url={documentUrls.view(document.id)}
          alt={document.original_filename}
          zoom={zoom}
          unsupportedMessage={
            document.content_type === 'image/heic' ? 'This browser cannot show HEIC photos. Use the download button above to open it on your device.' : undefined
          }
        />
      )}

      <ConfirmDialog
        open={confirmDelete}
        title="Delete this file?"
        message={`"${document.original_filename}" will be permanently deleted. This cannot be undone.`}
        loading={remove.isPending}
        error={remove.isError ? errorMessage(remove.error) : null}
        onCancel={() => {
          setConfirmDelete(false)
          remove.reset()
        }}
        onConfirm={() =>
          remove.mutate(document.id, {
            onSuccess: () => {
              toast.success('File deleted')
              navigate(recordPath, { replace: true })
            },
          })
        }
      />
    </div>
  )
}
