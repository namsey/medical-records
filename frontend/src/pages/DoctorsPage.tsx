import { Mail, Phone, Plus, Stethoscope } from 'lucide-react'
import { useState } from 'react'
import { DoctorForm } from '@/components/directories/DirectoryForms'
import { PageHeader } from '@/components/layout/PageHeader'
import { Button } from '@/components/ui/Button'
import { CardSkeletons, EmptyState, ErrorMessage } from '@/components/ui/feedback'
import { Modal } from '@/components/ui/Modal'
import { useToast } from '@/components/ui/Toast'
import { useDoctors } from '@/hooks/queries'
import { errorMessage } from '@/lib/api'
import { pluralize } from '@/lib/format'
import type { Doctor } from '@/lib/types'

type Editing = { doctor: Doctor | null } | null

export function DoctorsPage() {
  const { data: doctors, isPending, isError, error, refetch } = useDoctors()
  const [editing, setEditing] = useState<Editing>(null)
  const toast = useToast()

  return (
    <>
      <PageHeader
        title="Doctors"
        back="/profile"
        action={
          <Button size="sm" onClick={() => setEditing({ doctor: null })}>
            <Plus className="size-4" aria-hidden />
            Add
          </Button>
        }
      />

      {isPending && <CardSkeletons count={3} />}
      {isError && <ErrorMessage message={errorMessage(error)} onRetry={() => void refetch()} />}
      {doctors && doctors.length === 0 && (
        <EmptyState icon={Stethoscope} title="No doctors yet" description="Save the doctors you visit so you can pick them when adding records." action={<Button onClick={() => setEditing({ doctor: null })}>Add a doctor</Button>} />
      )}

      <ul className="space-y-3">
        {doctors?.map((doctor) => (
          <li key={doctor.id} className="card overflow-hidden">
            <button type="button" onClick={() => setEditing({ doctor })} className="block w-full p-4 text-left active:bg-wash">
              <p className="text-lg font-semibold leading-snug">{doctor.name}</p>
              {doctor.specialization && <p className="text-sm text-muted">{doctor.specialization}</p>}
              {doctor.hospital && <p className="text-sm text-muted">{doctor.hospital}</p>}
              <p className="mt-1 text-xs text-muted">{pluralize(doctor.record_count, 'record')}</p>
            </button>
            {(doctor.phone || doctor.email) && (
              <div className="flex flex-wrap gap-2 border-t border-line px-4 py-2">
                {doctor.phone && (
                  <a href={`tel:${doctor.phone}`} className="inline-flex min-h-11 items-center gap-1.5 text-sm font-semibold text-brand-700">
                    <Phone className="size-4" aria-hidden />
                    {doctor.phone}
                  </a>
                )}
                {doctor.email && (
                  <a href={`mailto:${doctor.email}`} className="inline-flex min-h-11 items-center gap-1.5 text-sm font-semibold text-brand-700">
                    <Mail className="size-4" aria-hidden />
                    Email
                  </a>
                )}
              </div>
            )}
          </li>
        ))}
      </ul>

      <Modal open={editing !== null} title={editing?.doctor ? 'Edit doctor' : 'New doctor'} onClose={() => setEditing(null)}>
        {editing && (
          <DoctorForm
            key={editing.doctor?.id ?? 'new'}
            initial={editing.doctor ?? undefined}
            onCancel={() => setEditing(null)}
            onSaved={() => {
              toast.success(editing.doctor ? 'Doctor updated' : 'Doctor added')
              setEditing(null)
            }}
            onDeleted={() => {
              toast.success('Doctor deleted')
              setEditing(null)
            }}
          />
        )}
      </Modal>
    </>
  )
}
