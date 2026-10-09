import { Download, Eye, FileText, Image as ImageIcon, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useDeleteDocument } from '@/hooks/queries'
import { documentUrls, errorMessage } from '@/lib/api'
import { formatFileSize } from '@/lib/format'
import type { DocumentInfo } from '@/lib/types'
import { buttonClasses } from '../ui/Button'
import { ConfirmDialog } from '../ui/Modal'
import { useToast } from '../ui/Toast'

interface DocumentListProps {
  documents: DocumentInfo[]
  /** Offer the Delete button (hidden while a form is saving, for example). */
  canDelete?: boolean
}

export function isPdf(document: Pick<DocumentInfo, 'content_type'>): boolean {
  return document.content_type === 'application/pdf'
}

export function DocumentList({ documents, canDelete = true }: DocumentListProps) {
  const [pendingDelete, setPendingDelete] = useState<DocumentInfo | null>(null)
  const remove = useDeleteDocument()
  const toast = useToast()

  if (documents.length === 0) return null

  return (
    <>
      <ul className="space-y-3">
        {documents.map((document) => {
          const Icon = isPdf(document) ? FileText : ImageIcon
          return (
            <li key={document.id} className="rounded-xl border border-line bg-white p-3">
              <div className="flex items-center gap-3">
                <span className={`grid size-11 shrink-0 place-items-center rounded-xl ${isPdf(document) ? 'bg-rose-100 text-rose-800' : 'bg-indigo-100 text-indigo-800'}`}>
                  <Icon className="size-5" aria-hidden />
                </span>
                <div className="min-w-0 flex-1">
                  <p className="truncate font-medium">{document.original_filename}</p>
                  <p className="text-xs text-muted">
                    {isPdf(document) ? 'PDF' : 'Image'} · {formatFileSize(document.size_bytes)}
                  </p>
                </div>
              </div>
              <div className="mt-3 grid grid-cols-3 gap-2">
                <Link to={`/documents/${document.id}`} className={buttonClasses('primary', 'sm')}>
                  <Eye className="size-4" aria-hidden />
                  View
                </Link>
                <a href={documentUrls.download(document.id)} download={document.original_filename} className={buttonClasses('secondary', 'sm')}>
                  <Download className="size-4" aria-hidden />
                  Download
                </a>
                {canDelete && (
                  <button type="button" onClick={() => setPendingDelete(document)} className={buttonClasses('dangerOutline', 'sm')}>
                    <Trash2 className="size-4" aria-hidden />
                    Delete
                  </button>
                )}
              </div>
            </li>
          )
        })}
      </ul>

      <ConfirmDialog
        open={pendingDelete !== null}
        title="Delete this file?"
        message={pendingDelete ? `"${pendingDelete.original_filename}" will be permanently deleted. This cannot be undone.` : ''}
        loading={remove.isPending}
        error={remove.isError ? errorMessage(remove.error) : null}
        onCancel={() => {
          setPendingDelete(null)
          remove.reset()
        }}
        onConfirm={() => {
          if (!pendingDelete) return
          remove.mutate(pendingDelete.id, {
            onSuccess: () => {
              setPendingDelete(null)
              toast.success('File deleted')
            },
          })
        }}
      />
    </>
  )
}
