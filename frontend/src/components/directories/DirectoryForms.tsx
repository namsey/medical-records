import { useState, type FormEvent } from 'react'
import { useDeleteDoctor, useDeleteLab, useSaveDoctor, useSaveLab } from '@/hooks/queries'
import { errorMessage } from '@/lib/api'
import { orNull } from '@/lib/format'
import type { Doctor, Lab } from '@/lib/types'
import { Button } from '../ui/Button'
import { ConfirmDialog } from '../ui/Modal'
import { TextArea, TextInput } from '../ui/Field'
import { ErrorMessage } from '../ui/feedback'

interface FormProps<T> {
  initial?: T
  onSaved: (saved: T) => void
  onCancel: () => void
  /** Called after a successful delete (edit mode only). */
  onDeleted?: () => void
}

export function DoctorForm({ initial, onSaved, onCancel, onDeleted }: FormProps<Doctor>) {
  const [name, setName] = useState(initial?.name ?? '')
  const [specialization, setSpecialization] = useState(initial?.specialization ?? '')
  const [hospital, setHospital] = useState(initial?.hospital ?? '')
  const [phone, setPhone] = useState(initial?.phone ?? '')
  const [email, setEmail] = useState(initial?.email ?? '')
  const [address, setAddress] = useState(initial?.address ?? '')
  const [notes, setNotes] = useState(initial?.notes ?? '')
  const [confirmDelete, setConfirmDelete] = useState(false)
  const save = useSaveDoctor()
  const remove = useDeleteDoctor()

  function submit(event: FormEvent) {
    event.preventDefault()
    save.mutate(
      {
        id: initial?.id,
        input: {
          name: name.trim(),
          specialization: orNull(specialization),
          hospital: orNull(hospital),
          phone: orNull(phone),
          email: orNull(email),
          address: orNull(address),
          notes: orNull(notes),
        },
      },
      { onSuccess: onSaved },
    )
  }

  return (
    <form onSubmit={submit} className="space-y-4">
      <TextInput label="Name" required value={name} onChange={(e) => setName(e.target.value)} maxLength={255} placeholder="Dr. Anita Sharma" autoComplete="off" />
      <TextInput label="Specialization" value={specialization} onChange={(e) => setSpecialization(e.target.value)} maxLength={255} placeholder="Endocrinologist" />
      <TextInput label="Hospital / clinic" value={hospital} onChange={(e) => setHospital(e.target.value)} maxLength={255} />
      <TextInput label="Phone" type="tel" inputMode="tel" value={phone} onChange={(e) => setPhone(e.target.value)} maxLength={50} />
      <TextInput label="Email" type="email" inputMode="email" value={email} onChange={(e) => setEmail(e.target.value)} maxLength={320} />
      <TextArea label="Address" value={address} onChange={(e) => setAddress(e.target.value)} rows={2} maxLength={10000} />
      <TextArea label="Notes" value={notes} onChange={(e) => setNotes(e.target.value)} maxLength={10000} />
      {save.isError && <ErrorMessage message={errorMessage(save.error)} />}
      <div className="grid grid-cols-2 gap-3">
        <Button variant="secondary" onClick={onCancel} disabled={save.isPending}>
          Cancel
        </Button>
        <Button type="submit" loading={save.isPending} disabled={!name.trim()}>
          Save
        </Button>
      </div>
      {initial && onDeleted && (
        <>
          <Button variant="dangerOutline" className="w-full" onClick={() => setConfirmDelete(true)}>
            Delete doctor
          </Button>
          <ConfirmDialog
            open={confirmDelete}
            title="Delete this doctor?"
            message={`${initial.name} will be removed from your directory. Records that use this doctor must be changed first.`}
            loading={remove.isPending}
            error={remove.isError ? errorMessage(remove.error) : null}
            onCancel={() => { setConfirmDelete(false); remove.reset() }}
            onConfirm={() => remove.mutate(initial.id, { onSuccess: () => { setConfirmDelete(false); onDeleted() } })}
          />
        </>
      )}
    </form>
  )
}

export function LabForm({ initial, onSaved, onCancel, onDeleted }: FormProps<Lab>) {
  const [name, setName] = useState(initial?.name ?? '')
  const [address, setAddress] = useState(initial?.address ?? '')
  const [phone, setPhone] = useState(initial?.phone ?? '')
  const [notes, setNotes] = useState(initial?.notes ?? '')
  const [confirmDelete, setConfirmDelete] = useState(false)
  const save = useSaveLab()
  const remove = useDeleteLab()

  function submit(event: FormEvent) {
    event.preventDefault()
    save.mutate(
      { id: initial?.id, input: { name: name.trim(), address: orNull(address), phone: orNull(phone), notes: orNull(notes) } },
      { onSuccess: onSaved },
    )
  }

  return (
    <form onSubmit={submit} className="space-y-4">
      <TextInput label="Name" required value={name} onChange={(e) => setName(e.target.value)} maxLength={255} placeholder="City Diagnostics" autoComplete="off" />
      <TextArea label="Address" value={address} onChange={(e) => setAddress(e.target.value)} rows={2} maxLength={10000} />
      <TextInput label="Phone" type="tel" inputMode="tel" value={phone} onChange={(e) => setPhone(e.target.value)} maxLength={50} />
      <TextArea label="Notes" value={notes} onChange={(e) => setNotes(e.target.value)} maxLength={10000} />
      {save.isError && <ErrorMessage message={errorMessage(save.error)} />}
      <div className="grid grid-cols-2 gap-3">
        <Button variant="secondary" onClick={onCancel} disabled={save.isPending}>
          Cancel
        </Button>
        <Button type="submit" loading={save.isPending} disabled={!name.trim()}>
          Save
        </Button>
      </div>
      {initial && onDeleted && (
        <>
          <Button variant="dangerOutline" className="w-full" onClick={() => setConfirmDelete(true)}>
            Delete laboratory
          </Button>
          <ConfirmDialog
            open={confirmDelete}
            title="Delete this laboratory?"
            message={`${initial.name} will be removed from your directory. Lab reports that use it must be changed first.`}
            loading={remove.isPending}
            error={remove.isError ? errorMessage(remove.error) : null}
            onCancel={() => { setConfirmDelete(false); remove.reset() }}
            onConfirm={() => remove.mutate(initial.id, { onSuccess: () => { setConfirmDelete(false); onDeleted() } })}
          />
        </>
      )}
    </form>
  )
}
