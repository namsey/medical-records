import { Plus } from 'lucide-react'
import { useState, type ReactNode } from 'react'
import { useDoctors, useLabs } from '@/hooks/queries'
import type { Doctor, Lab } from '@/lib/types'
import { DoctorForm, LabForm } from '../directories/DirectoryForms'
import { Modal } from '../ui/Modal'
import { SelectInput } from '../ui/Field'

interface PickerProps<T extends { id: string; name: string }> {
  label: string
  noun: string
  items: T[] | undefined
  value: string
  onChange: (id: string, item: T | undefined) => void
  describe?: (item: T) => string
  renderForm: (handlers: { onSaved: (item: T) => void; onCancel: () => void }) => ReactNode
}

/** A native select (best on phones) plus a quick "add new" sheet, so records can be filed without leaving the form. */
function DirectoryPicker<T extends { id: string; name: string }>({ label, noun, items, value, onChange, describe, renderForm }: PickerProps<T>) {
  const [adding, setAdding] = useState(false)
  return (
    <div className="space-y-1">
      <SelectInput label={label} value={value} onChange={(event) => onChange(event.target.value, items?.find((item) => item.id === event.target.value))}>
        <option value="">Not specified</option>
        {items?.map((item) => (
          <option key={item.id} value={item.id}>
            {describe ? describe(item) : item.name}
          </option>
        ))}
      </SelectInput>
      <button type="button" onClick={() => setAdding(true)} className="inline-flex min-h-11 items-center gap-1.5 rounded-lg px-1 text-sm font-semibold text-brand-700">
        <Plus className="size-4" aria-hidden />
        Add new {noun}
      </button>
      <Modal open={adding} title={`New ${noun}`} onClose={() => setAdding(false)}>
        {renderForm({
          onSaved: (item) => {
            setAdding(false)
            onChange(item.id, item)
          },
          onCancel: () => setAdding(false),
        })}
      </Modal>
    </div>
  )
}

interface SpecificPickerProps<T> {
  label: string
  value: string
  onChange: (id: string, item: T | undefined) => void
}

export function DoctorPicker(props: SpecificPickerProps<Doctor>) {
  const { data } = useDoctors()
  return (
    <DirectoryPicker<Doctor>
      {...props}
      noun="doctor"
      items={data}
      describe={(doctor) => (doctor.specialization ? `${doctor.name} (${doctor.specialization})` : doctor.name)}
      renderForm={(handlers) => <DoctorForm {...handlers} />}
    />
  )
}

export function LabPicker(props: SpecificPickerProps<Lab>) {
  const { data } = useLabs()
  return <DirectoryPicker<Lab> {...props} noun="laboratory" items={data} renderForm={(handlers) => <LabForm {...handlers} />} />
}
