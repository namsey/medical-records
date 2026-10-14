import { X } from 'lucide-react'
import { useEffect, useRef, useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { useGoBack } from '@/hooks/useGoBack'
import { uploadDocument, useCreateRecord, useDoctors, useInvalidateRecordData, useUpdateRecord } from '@/hooks/queries'
import { errorMessage } from '@/lib/api'
import { FORM_CONFIG, TITLE_REQUIRED, changeRecordType, droppedDetails, fieldLabel, formToInput, validateForm, type FieldKey, type RecordFormState } from '@/lib/recordForm'
import { RECORD_TYPES, RECORD_TYPE_INFO } from '@/lib/recordTypes'
import { suggestRecordType } from '@/lib/typeSuggestion'
import type { Doctor, MedicalRecord, RecordType } from '@/lib/types'
import { DocumentList } from '../documents/DocumentList'
import { PageHeader } from '../layout/PageHeader'
import { FilePicker } from '../documents/FilePicker'
import { Button } from '../ui/Button'
import { ErrorMessage } from '../ui/feedback'
import { ConfirmDialog } from '../ui/Modal'
import { FormSection, SelectInput, TextArea, TextInput } from '../ui/Field'
import { useToast } from '../ui/Toast'
import { DoctorPicker, LabPicker } from './DirectoryPicker'
import { LabResultsEditor, MedicinesEditor } from './ListEditors'
import { TagInput } from './TagInput'

interface RecordFormProps {
  initial: RecordFormState
  /** Present when editing; absent when creating. */
  existing?: MedicalRecord
}

type TextKey = Exclude<FieldKey, 'doctor' | 'lab'>

const TEXT_AREAS: Partial<Record<TextKey, number>> = {
  reason: 2,
  symptoms: 3,
  diagnosis: 2,
  description: 3,
  treatment: 3,
  doctorNotes: 3,
  summary: 3,
}

const TEXT_KEYS: Record<TextKey, keyof RecordFormState> = {
  title: 'title',
  hospital: 'hospital',
  specialization: 'specialization',
  reason: 'reason',
  symptoms: 'symptoms',
  diagnosis: 'diagnosis',
  description: 'description',
  treatment: 'treatment',
  doctorNotes: 'doctorNotes',
  summary: 'summary',
  testName: 'testName',
  followUpDate: 'followUpDate',
  reportDate: 'reportDate',
}

export function RecordForm({ initial, existing }: RecordFormProps) {
  const [form, setForm] = useState(initial)
  const [files, setFiles] = useState<File[]>([])
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [submitError, setSubmitError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [progress, setProgress] = useState<string | null>(null)
  const [confirmingLeave, setConfirmingLeave] = useState(false)
  const [confirmingDrop, setConfirmingDrop] = useState(false)
  const [dismissedSuggestion, setDismissedSuggestion] = useState<RecordType | null>(null)
  const topRef = useRef<HTMLDivElement>(null)
  const navigate = useNavigate()
  const toast = useToast()
  const create = useCreateRecord()
  const update = useUpdateRecord(existing?.id ?? '')
  const invalidate = useInvalidateRecordData()
  const goBack = useGoBack(existing ? `/records/${existing.id}` : '/')
  useDoctors() // warm the directory so the pickers render instantly

  const dirty = files.length > 0 || JSON.stringify(form) !== JSON.stringify(initial)

  // Reloading or closing the tab with unsaved changes asks the browser to confirm.
  useEffect(() => {
    if (!dirty || saving) return
    const onBeforeUnload = (event: BeforeUnloadEvent) => event.preventDefault()
    window.addEventListener('beforeunload', onBeforeUnload)
    return () => window.removeEventListener('beforeunload', onBeforeUnload)
  }, [dirty, saving])

  function leave() {
    if (dirty) setConfirmingLeave(true)
    else goBack()
  }

  const config = FORM_CONFIG[form.recordType]
  const titleRequired = TITLE_REQUIRED.includes(form.recordType)
  const typeLabel = RECORD_TYPE_INFO[form.recordType].label
  const dropped = droppedDetails(form, initial.recordType)
  // When adding, suggest a type from the title; never switch on the user's behalf.
  const suggested = existing ? null : suggestRecordType(form.title)
  const suggestion = suggested && suggested !== form.recordType && suggested !== dismissedSuggestion ? suggested : null

  function set<K extends keyof RecordFormState>(key: K, value: RecordFormState[K]) {
    setForm((previous) => ({ ...previous, [key]: value }))
  }

  function chooseDoctor(id: string, doctor: Doctor | undefined) {
    setForm((previous) => ({
      ...previous,
      doctorId: id,
      // Pre-fill from the directory, but never overwrite what the user already typed.
      hospital: previous.hospital || doctor?.hospital || '',
      specialization: previous.specialization || doctor?.specialization || '',
    }))
  }

  function submit(event: FormEvent) {
    event.preventDefault()
    setSubmitError(null)
    const found = validateForm(form)
    setErrors(found)
    if (Object.keys(found).length > 0) {
      setSubmitError('Please fix the highlighted fields.')
      topRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
      return
    }
    // A changed record type can leave details the new type does not store; never drop them silently.
    if (dropped.length > 0) setConfirmingDrop(true)
    else void save()
  }

  async function save() {
    setSaving(true)
    try {
      const input = formToInput(form)
      const record = existing ? await update.mutateAsync(input) : await create.mutateAsync(input)

      const failures: string[] = []
      for (const [index, file] of files.entries()) {
        setProgress(`Uploading file ${index + 1} of ${files.length}…`)
        try {
          await uploadDocument(record.id, file)
        } catch (error) {
          failures.push(errorMessage(error))
        }
      }
      if (files.length > 0) await invalidate()

      if (failures.length > 0) toast.error(`Record saved, but some files were not uploaded:\n${failures.join('\n')}`)
      else toast.success(existing ? 'Record updated' : 'Record saved')
      navigate(`/records/${record.id}`, { replace: true })
    } catch (error) {
      setSubmitError(errorMessage(error))
      topRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    } finally {
      setSaving(false)
      setProgress(null)
    }
  }

  function renderField(field: FieldKey) {
    const label = fieldLabel(form.recordType, field)
    const required = config.required.includes(field)
    if (field === 'doctor') {
      return <DoctorPicker key={field} label={label} value={form.doctorId} onChange={chooseDoctor} />
    }
    if (field === 'lab') {
      return <LabPicker key={field} label={label} value={form.labId} onChange={(id) => set('labId', id)} />
    }
    const stateKey = TEXT_KEYS[field]
    const value = form[stateKey] as string
    const onChange = (next: string) => set(stateKey, next as never)
    const error = errors[field]
    if (field === 'followUpDate' || field === 'reportDate') {
      return <TextInput key={field} label={label} type="date" value={value} onChange={(e) => onChange(e.target.value)} />
    }
    const rows = TEXT_AREAS[field]
    if (rows) {
      return <TextArea key={field} label={label} required={required} rows={rows} value={value} maxLength={10000} hint={config.hints?.[field]} error={error} onChange={(e) => onChange(e.target.value)} />
    }
    const placeholders: Partial<Record<TextKey, string>> = { testName: 'e.g. Vitamin B12, CBC, Lipid profile', hospital: 'Hospital or clinic name', specialization: 'e.g. Cardiology' }
    return <TextInput key={field} label={label} required={required} value={value} maxLength={255} placeholder={placeholders[field]} error={error} onChange={(e) => onChange(e.target.value)} />
  }

  return (
    <>
      <PageHeader title={existing ? 'Edit record' : `New ${typeLabel.toLowerCase()}`} onBack={saving ? undefined : leave} backIcon={existing ? 'arrow' : 'close'} />
      <form onSubmit={submit} noValidate className="space-y-4">
        <div ref={topRef} className="scroll-mt-20" />
        {submitError && <ErrorMessage message={submitError} />}

        <FormSection>
          <SelectInput label="Record type" value={form.recordType} onChange={(e) => setForm((previous) => changeRecordType(previous, e.target.value as RecordType))}>
            {RECORD_TYPES.map((type) => (
              <option key={type} value={type}>
                {RECORD_TYPE_INFO[type].label}
              </option>
            ))}
          </SelectInput>
          {dropped.length > 0 && (
            <p role="status" className="rounded-xl bg-amber-50 p-3 text-sm text-amber-900">
              A {typeLabel.toLowerCase()} does not keep: {dropped.join(', ')}. They will be removed when you save. Switch back to {RECORD_TYPE_INFO[initial.recordType].label} to keep them.
            </p>
          )}
          <TextInput
            label="Title"
            required={titleRequired}
            value={form.title}
            maxLength={255}
            error={errors.title}
            hint={titleRequired ? undefined : 'Optional. Leave blank to name it automatically.'}
            placeholder={form.recordType === 'scan' ? 'e.g. Knee MRI' : RECORD_TYPE_INFO[form.recordType].label}
            onChange={(e) => set('title', e.target.value)}
          />
          {suggestion && (
            <div role="status" className="flex items-center gap-2 rounded-xl bg-brand-50 py-1 pl-3 pr-1 text-sm text-brand-800">
              <p className="min-w-0 flex-1">This looks like a {RECORD_TYPE_INFO[suggestion].label.toLowerCase()}.</p>
              <Button variant="ghost" size="sm" onClick={() => setForm((previous) => changeRecordType(previous, suggestion))}>
                Switch to {RECORD_TYPE_INFO[suggestion].label}
              </Button>
              <button type="button" onClick={() => setDismissedSuggestion(suggestion)} aria-label="Dismiss suggestion" className="grid size-10 shrink-0 place-items-center rounded-full hover:bg-brand-100">
                <X className="size-4" aria-hidden />
              </button>
            </div>
          )}
          <TextInput label={config.dateLabel} type="date" required value={form.recordDate} error={errors.recordDate} onChange={(e) => set('recordDate', e.target.value)} />
          {config.fields.map(renderField)}
        </FormSection>

        {config.medicines && (
          <FormSection>
            <MedicinesEditor medicines={form.medicines} errors={errors} onChange={(next) => set('medicines', next)} />
          </FormSection>
        )}
        {config.results && (
          <FormSection>
            <LabResultsEditor results={form.results} errors={errors} onChange={(next) => set('results', next)} />
          </FormSection>
        )}

        <FormSection title="Notes and tags">
          <TextArea label="Personal notes" rows={3} value={form.personalNotes} maxLength={10000} hint="Only you see these. Anything you want to remember." onChange={(e) => set('personalNotes', e.target.value)} />
          <TagInput tags={form.tags} onChange={(next) => set('tags', next)} />
        </FormSection>

        <FormSection title="Attachments">
          {existing && existing.documents.length > 0 && <DocumentList documents={existing.documents} canDelete={!saving} />}
          <FilePicker label={existing ? 'Add more files' : 'Files'} files={files} onChange={setFiles} disabled={saving} />
        </FormSection>

        <div className="grid grid-cols-2 gap-3 pt-2">
          <Button variant="secondary" disabled={saving} onClick={leave}>
            Cancel
          </Button>
          <Button type="submit" loading={saving}>
            {saving ? (progress ?? 'Saving…') : existing ? 'Save changes' : 'Save record'}
          </Button>
        </div>
      </form>
      <ConfirmDialog
        open={confirmingDrop}
        title="Remove details?"
        message={`Saving as a ${typeLabel.toLowerCase()} removes: ${dropped.join(', ')}.`}
        confirmLabel="Save and remove"
        cancelLabel="Go back"
        onConfirm={() => {
          setConfirmingDrop(false)
          void save()
        }}
        onCancel={() => setConfirmingDrop(false)}
      />
      <ConfirmDialog
        open={confirmingLeave}
        title="Discard changes?"
        message={existing ? 'Your changes to this record will not be saved.' : 'This record has not been saved. What you entered will be lost.'}
        confirmLabel="Discard"
        cancelLabel="Keep editing"
        onConfirm={() => {
          setConfirmingLeave(false)
          goBack()
        }}
        onCancel={() => setConfirmingLeave(false)}
      />
    </>
  )
}
