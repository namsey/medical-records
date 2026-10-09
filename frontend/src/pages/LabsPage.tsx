import { FlaskConical, MapPin, Phone, Plus } from 'lucide-react'
import { useState } from 'react'
import { LabForm } from '@/components/directories/DirectoryForms'
import { PageHeader } from '@/components/layout/PageHeader'
import { Button } from '@/components/ui/Button'
import { CardSkeletons, EmptyState, ErrorMessage } from '@/components/ui/feedback'
import { Modal } from '@/components/ui/Modal'
import { useToast } from '@/components/ui/Toast'
import { useLabs } from '@/hooks/queries'
import { errorMessage } from '@/lib/api'
import { pluralize } from '@/lib/format'
import type { Lab } from '@/lib/types'

type Editing = { lab: Lab | null } | null

export function LabsPage() {
  const { data: labs, isPending, isError, error, refetch } = useLabs()
  const [editing, setEditing] = useState<Editing>(null)
  const toast = useToast()

  return (
    <>
      <PageHeader
        title="Laboratories"
        back="/more"
        action={
          <Button size="sm" onClick={() => setEditing({ lab: null })}>
            <Plus className="size-4" aria-hidden />
            Add
          </Button>
        }
      />

      {isPending && <CardSkeletons count={3} />}
      {isError && <ErrorMessage message={errorMessage(error)} onRetry={() => void refetch()} />}
      {labs && labs.length === 0 && (
        <EmptyState icon={FlaskConical} title="No laboratories yet" description="Save the labs you use so you can pick them when adding lab reports." action={<Button onClick={() => setEditing({ lab: null })}>Add a laboratory</Button>} />
      )}

      <ul className="space-y-3">
        {labs?.map((lab) => (
          <li key={lab.id} className="card overflow-hidden">
            <button type="button" onClick={() => setEditing({ lab })} className="block w-full p-4 text-left active:bg-wash">
              <p className="text-lg font-semibold leading-snug">{lab.name}</p>
              {lab.address && (
                <p className="mt-0.5 flex items-start gap-1.5 text-sm text-muted">
                  <MapPin className="mt-0.5 size-4 shrink-0" aria-hidden />
                  <span className="whitespace-pre-line">{lab.address}</span>
                </p>
              )}
              <p className="mt-1 text-xs text-muted">{pluralize(lab.record_count, 'record')}</p>
            </button>
            {lab.phone && (
              <div className="border-t border-line px-4 py-2">
                <a href={`tel:${lab.phone}`} className="inline-flex min-h-11 items-center gap-1.5 text-sm font-semibold text-brand-700">
                  <Phone className="size-4" aria-hidden />
                  {lab.phone}
                </a>
              </div>
            )}
          </li>
        ))}
      </ul>

      <Modal open={editing !== null} title={editing?.lab ? 'Edit laboratory' : 'New laboratory'} onClose={() => setEditing(null)}>
        {editing && (
          <LabForm
            key={editing.lab?.id ?? 'new'}
            initial={editing.lab ?? undefined}
            onCancel={() => setEditing(null)}
            onSaved={() => {
              toast.success(editing.lab ? 'Laboratory updated' : 'Laboratory added')
              setEditing(null)
            }}
            onDeleted={() => {
              toast.success('Laboratory deleted')
              setEditing(null)
            }}
          />
        )}
      </Modal>
    </>
  )
}
