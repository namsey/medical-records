import { useEffect, useRef, useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { useGoBack } from '@/hooks/useGoBack'
import { uploadDocument, useCreateRecord, useDoctors, useInvalidateRecordData, useUpdateRecord } from '@/hooks/queries'
import { errorMessage } from '@/lib/api'
import { FORM_CONFIG, TITLE_REQUIRED, fieldLabel, formToInput, validateForm, type FieldKey, type RecordFormState } from '@/lib/recordForm'
import { RECORD_TYPE_INFO } from '@/lib/recordTypes'
import type { Doctor, MedicalRecord } from '@/lib/types'
import { DocumentList } from '../documents/DocumentList'
import { PageHeader } from '../layout/PageHeader'
import { FilePicker } from '../documents/FilePicker'
import { Button } from '../ui/Button'
import { ErrorMessage } from '../ui/feedback'
import { ConfirmDialog } from '../ui/Modal'
import { FormSection, TextArea, TextInput } from '../ui/Field'
import { useToast } from '../ui/Toast'
import { DoctorPicker, LabPicker } from './DirectoryPicker'
import { LabResultsEditor, MedicinesEditor } from './ListEditors'
import { TagInput } from './TagInput'
import { TypeBadge } from './RecordCard'

interface RecordFormProps {
  /** Page title shown in the form's header. */
  title: string
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

export function RecordForm({ title, initial, existing }: RecordFormProps) {
  const [form, setForm] = useState(initial)
  const [files, setFiles] = useState<File[]>([])
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [submitError, setSubmitError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [progress, setProgress] = useState<string | null>(null)
  const [confirmingLeave, setConfirmingLeave] = useState(false)
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

  async function submit(event: FormEvent) {
    event.preventDefault()
    setSubmitError(null)
    const found = validateForm(form)
    setErrors(found)
    if (Object.keys(found).length > 0) {
      setSubmitError('Please fix the highlighted fields.')
      topRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
      return
    }

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
      <PageHeader title={title} onBack={saving ? undefined : leave} backIcon={existing ? 'arrow' : 'close'} />
      <form onSubmit={submit} noValidate className="space-y-4">
        <div ref={topRef} className="scroll-mt-20" />
        <div className="flex items-center gap-2">
          <TypeBadge type={form.recordType} />
          {existing && <span className="text-sm text-muted">Editing</span>}
        </div>

        {submitError && <ErrorMessage message={submitError} />}

        <FormSection>
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
