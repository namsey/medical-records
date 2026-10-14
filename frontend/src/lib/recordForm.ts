import { orNull, pluralize, todayIso } from './format'
import type { LabResult, Medicine, MedicalRecord, RecordInput, RecordType } from './types'

export type FieldKey =
  | 'title'
  | 'doctor'
  | 'lab'
  | 'hospital'
  | 'specialization'
  | 'reason'
  | 'symptoms'
  | 'diagnosis'
  | 'description'
  | 'treatment'
  | 'doctorNotes'
  | 'summary'
  | 'testName'
  | 'followUpDate'
  | 'reportDate'

export interface MedicineForm {
  key: string
  name: string
  dosage: string
  frequency: string
  duration: string
  startDate: string
  endDate: string
  instructions: string
}

export interface ResultForm {
  key: string
  parameter: string
  value: string
  unit: string
  referenceRange: string
  flag: string
}

export interface RecordFormState {
  recordType: RecordType
  title: string
  recordDate: string
  doctorId: string
  labId: string
  hospital: string
  specialization: string
  reason: string
  symptoms: string
  diagnosis: string
  description: string
  treatment: string
  doctorNotes: string
  summary: string
  personalNotes: string
  testName: string
  followUpDate: string
  reportDate: string
  tags: string[]
  medicines: MedicineForm[]
  results: ResultForm[]
}

export interface TypeFormConfig {
  dateLabel: string
  /** Fields shown, in order (title, tags, personal notes and attachments are always handled by the form). */
  fields: FieldKey[]
  required: FieldKey[]
  labels: Partial<Record<FieldKey, string>>
  hints?: Partial<Record<FieldKey, string>>
  medicines?: boolean
  results?: boolean
}

const DEFAULT_LABELS: Record<FieldKey, string> = {
  title: 'Title',
  doctor: 'Doctor',
  lab: 'Laboratory',
  hospital: 'Hospital / clinic',
  specialization: 'Specialization',
  reason: 'Reason',
  symptoms: 'Symptoms',
  diagnosis: 'Diagnosis',
  description: 'Description',
  treatment: 'Treatment',
  doctorNotes: "Doctor's notes",
  summary: 'Summary',
  testName: 'Test name',
  followUpDate: 'Follow-up date',
  reportDate: 'Report date',
}

export const FORM_CONFIG: Record<RecordType, TypeFormConfig> = {
  doctor_visit: {
    dateLabel: 'Visit date',
    fields: ['doctor', 'specialization', 'hospital', 'reason', 'symptoms', 'diagnosis', 'doctorNotes', 'followUpDate'],
    required: [],
    labels: { doctor: 'Doctor', reason: 'Reason for visit', doctorNotes: "Doctor's notes", followUpDate: 'Follow-up date' },
  },
  prescription: {
    dateLabel: 'Prescription date',
    fields: ['doctor', 'hospital', 'reason', 'doctorNotes'],
    required: [],
    labels: { doctor: 'Doctor', reason: 'Diagnosis / reason', doctorNotes: "Doctor's instructions" },
    medicines: true,
  },
  lab_report: {
    dateLabel: 'Test date',
    fields: ['testName', 'lab', 'doctor', 'reportDate', 'reason', 'summary'],
    required: ['testName'],
    labels: { testName: 'Test name', lab: 'Laboratory', doctor: 'Referring doctor', reportDate: 'Report date', reason: 'Reason for test', summary: 'Summary' },
    hints: { summary: 'Copy the summary printed on the report. The app does not interpret results.' },
    results: true,
  },
  diagnosis: {
    dateLabel: 'Date',
    fields: ['diagnosis', 'doctor', 'description', 'treatment'],
    required: ['diagnosis'],
    labels: { diagnosis: 'Diagnosis', doctor: 'Diagnosed by' },
  },
  medical_document: {
    dateLabel: 'Document date',
    fields: ['doctor', 'hospital', 'description'],
    required: [],
    labels: { doctor: 'Doctor', description: 'Description' },
  },
  scan: {
    dateLabel: 'Scan date',
    fields: ['doctor', 'hospital', 'description'],
    required: [],
    labels: { doctor: 'Referring doctor', description: 'Findings / description' },
  },
  other: {
    dateLabel: 'Date',
    fields: ['doctor', 'hospital', 'description'],
    required: [],
    labels: { doctor: 'Doctor', description: 'Description' },
  },
}

/** The label for a field on a given record type (type-specific wording first, then the default). */
export function fieldLabel(type: RecordType, field: FieldKey): string {
  return FORM_CONFIG[type].labels[field] ?? DEFAULT_LABELS[field]
}

/** Types where nothing else identifies the record, so the user must name it. */
export const TITLE_REQUIRED: RecordType[] = ['medical_document', 'scan', 'other']

let keyCounter = 0
const nextKey = () => `k${++keyCounter}`

export function emptyMedicine(): MedicineForm {
  return { key: nextKey(), name: '', dosage: '', frequency: '', duration: '', startDate: '', endDate: '', instructions: '' }
}

export function emptyResult(): ResultForm {
  return { key: nextKey(), parameter: '', value: '', unit: '', referenceRange: '', flag: '' }
}

export function emptyForm(recordType: RecordType): RecordFormState {
  return {
    recordType,
    title: '',
    recordDate: todayIso(),
    doctorId: '',
    labId: '',
    hospital: '',
    specialization: '',
    reason: '',
    symptoms: '',
    diagnosis: '',
    description: '',
    treatment: '',
    doctorNotes: '',
    summary: '',
    personalNotes: '',
    testName: '',
    followUpDate: '',
    reportDate: '',
    tags: [],
    medicines: recordType === 'prescription' ? [emptyMedicine()] : [],
    results: recordType === 'lab_report' ? [emptyResult()] : [],
  }
}

export function formFromRecord(record: MedicalRecord): RecordFormState {
  return {
    recordType: record.record_type,
    title: record.title,
    recordDate: record.record_date,
    doctorId: record.doctor_id ?? '',
    labId: record.lab_id ?? '',
    hospital: record.hospital ?? '',
    specialization: record.specialization ?? '',
    reason: record.reason ?? '',
    symptoms: record.symptoms ?? '',
    diagnosis: record.diagnosis ?? '',
    description: record.description ?? '',
    treatment: record.treatment ?? '',
    doctorNotes: record.doctor_notes ?? '',
    summary: record.summary ?? '',
    personalNotes: record.personal_notes ?? '',
    testName: record.test_name ?? '',
    followUpDate: record.follow_up_date ?? '',
    reportDate: record.report_date ?? '',
    tags: record.tags,
    medicines: record.medicines.map((m) => ({
      key: nextKey(),
      name: m.name,
      dosage: m.dosage ?? '',
      frequency: m.frequency ?? '',
      duration: m.duration ?? '',
      startDate: m.start_date ?? '',
      endDate: m.end_date ?? '',
      instructions: m.instructions ?? '',
    })),
    results: record.results.map((r) => ({
      key: nextKey(),
      parameter: r.parameter,
      value: r.value ?? '',
      unit: r.unit ?? '',
      referenceRange: r.reference_range ?? '',
      flag: r.flag ?? '',
    })),
  }
}

/** Convert the form into an API payload. Fields the record type does not use are sent as null. */
export function formToInput(form: RecordFormState): RecordInput {
  const config = FORM_CONFIG[form.recordType]
  const uses = (field: FieldKey) => config.fields.includes(field)
  const text = (field: FieldKey, value: string) => (uses(field) ? orNull(value) : null)

  const medicines: Medicine[] = config.medicines
    ? form.medicines
        .filter((m) => m.name.trim() !== '')
        .map((m) => ({
          name: m.name.trim(),
          dosage: orNull(m.dosage),
          frequency: orNull(m.frequency),
          duration: orNull(m.duration),
          start_date: m.startDate || null,
          end_date: m.endDate || null,
          instructions: orNull(m.instructions),
        }))
    : []

  const results: LabResult[] = config.results
    ? form.results
        .filter((r) => r.parameter.trim() !== '')
        .map((r) => ({
          parameter: r.parameter.trim(),
          value: orNull(r.value),
          unit: orNull(r.unit),
          reference_range: orNull(r.referenceRange),
          flag: orNull(r.flag),
        }))
    : []

  return {
    record_type: form.recordType,
    title: orNull(form.title),
    record_date: form.recordDate,
    doctor_id: uses('doctor') && form.doctorId ? form.doctorId : null,
    lab_id: uses('lab') && form.labId ? form.labId : null,
    hospital: text('hospital', form.hospital),
    specialization: text('specialization', form.specialization),
    reason: text('reason', form.reason),
    symptoms: text('symptoms', form.symptoms),
    diagnosis: text('diagnosis', form.diagnosis),
    description: text('description', form.description),
    treatment: text('treatment', form.treatment),
    doctor_notes: text('doctorNotes', form.doctorNotes),
    summary: text('summary', form.summary),
    personal_notes: orNull(form.personalNotes),
    test_name: text('testName', form.testName),
    follow_up_date: uses('followUpDate') && form.followUpDate ? form.followUpDate : null,
    report_date: uses('reportDate') && form.reportDate ? form.reportDate : null,
    tags: form.tags,
    medicines,
    results,
  }
}

/** Where each type-specific field keeps its value in the form state. */
const FIELD_STATE: Record<Exclude<FieldKey, 'title'>, keyof RecordFormState> = {
  doctor: 'doctorId',
  lab: 'labId',
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

/** Switch the form to another record type. Values stay in the form, so switching back restores them. */
export function changeRecordType(form: RecordFormState, recordType: RecordType): RecordFormState {
  return {
    ...form,
    recordType,
    medicines: recordType === 'prescription' && form.medicines.length === 0 ? [emptyMedicine()] : form.medicines,
    results: recordType === 'lab_report' && form.results.length === 0 ? [emptyResult()] : form.results,
  }
}

/**
 * Details the form holds that its current record type does not store, so saving would drop them
 * (e.g. medicines after switching a prescription to a scan). Labels use the wording of `previousType`.
 */
export function droppedDetails(form: RecordFormState, previousType: RecordType): string[] {
  const config = FORM_CONFIG[form.recordType]
  const dropped: string[] = []
  for (const [field, stateKey] of Object.entries(FIELD_STATE) as [Exclude<FieldKey, 'title'>, keyof RecordFormState][]) {
    const value = form[stateKey]
    if (config.fields.includes(field) || typeof value !== 'string' || !value.trim()) continue
    const labelType = FORM_CONFIG[previousType].fields.includes(field)
      ? previousType
      : ((Object.keys(FORM_CONFIG) as RecordType[]).find((type) => FORM_CONFIG[type].fields.includes(field)) ?? previousType)
    dropped.push(fieldLabel(labelType, field))
  }
  const medicines = form.medicines.filter((m) => m.name.trim()).length
  if (!config.medicines && medicines > 0) dropped.push(pluralize(medicines, 'medicine'))
  const results = form.results.filter((r) => r.parameter.trim()).length
  if (!config.results && results > 0) dropped.push(pluralize(results, 'test result'))
  return dropped
}

/** Client-side checks for the fields the server also requires. Returns field -> message. */
export function validateForm(form: RecordFormState): Record<string, string> {
  const errors: Record<string, string> = {}
  const config = FORM_CONFIG[form.recordType]
  if (!form.recordDate) errors.recordDate = `${config.dateLabel} is required`
  if (TITLE_REQUIRED.includes(form.recordType) && !form.title.trim()) errors.title = 'Give this record a title'
  for (const field of config.required) {
    const value = form[field as keyof RecordFormState]
    if (typeof value === 'string' && !value.trim()) errors[field] = `${fieldLabel(form.recordType, field)} is required`
  }
  form.medicines.forEach((m) => {
    const touched = [m.dosage, m.frequency, m.duration, m.startDate, m.endDate, m.instructions].some((v) => v.trim() !== '')
    if (touched && !m.name.trim()) errors[`medicine-${m.key}`] = 'Enter the medicine name'
    if (m.startDate && m.endDate && m.endDate < m.startDate) errors[`medicine-${m.key}`] = 'End date is before the start date'
  })
  form.results.forEach((r) => {
    const touched = [r.value, r.unit, r.referenceRange, r.flag].some((v) => v.trim() !== '')
    if (touched && !r.parameter.trim()) errors[`result-${r.key}`] = 'Enter the parameter name'
  })
  return errors
}
