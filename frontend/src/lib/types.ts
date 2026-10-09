export type RecordType =
  | 'doctor_visit'
  | 'prescription'
  | 'lab_report'
  | 'diagnosis'
  | 'medical_document'
  | 'scan'
  | 'other'

export interface User {
  email: string
  name: string | null
}

export interface Doctor {
  id: string
  name: string
  specialization: string | null
  hospital: string | null
  phone: string | null
  email: string | null
  address: string | null
  notes: string | null
  record_count: number
}

export interface DoctorInput {
  name: string
  specialization: string | null
  hospital: string | null
  phone: string | null
  email: string | null
  address: string | null
  notes: string | null
}

export interface Lab {
  id: string
  name: string
  address: string | null
  phone: string | null
  notes: string | null
  record_count: number
}

export interface LabInput {
  name: string
  address: string | null
  phone: string | null
  notes: string | null
}

export interface Medicine {
  id?: string
  name: string
  dosage: string | null
  frequency: string | null
  duration: string | null
  start_date: string | null
  end_date: string | null
  instructions: string | null
}

export interface LabResult {
  id?: string
  parameter: string
  value: string | null
  unit: string | null
  reference_range: string | null
  flag: string | null
}

export interface DocumentInfo {
  id: string
  record_id: string
  original_filename: string
  content_type: string
  size_bytes: number
  created_at: string
}

export interface MedicalRecord {
  id: string
  record_type: RecordType
  title: string
  record_date: string
  doctor_id: string | null
  lab_id: string | null
  doctor: Doctor | null
  lab: Lab | null
  hospital: string | null
  specialization: string | null
  reason: string | null
  symptoms: string | null
  diagnosis: string | null
  description: string | null
  treatment: string | null
  doctor_notes: string | null
  summary: string | null
  personal_notes: string | null
  test_name: string | null
  follow_up_date: string | null
  report_date: string | null
  tags: string[]
  medicines: Medicine[]
  results: LabResult[]
  documents: DocumentInfo[]
  created_at: string
  updated_at: string
}

/** What the API accepts when creating or replacing a record. */
export interface RecordInput {
  record_type: RecordType
  title: string | null
  record_date: string
  doctor_id: string | null
  lab_id: string | null
  hospital: string | null
  specialization: string | null
  reason: string | null
  symptoms: string | null
  diagnosis: string | null
  description: string | null
  treatment: string | null
  doctor_notes: string | null
  summary: string | null
  personal_notes: string | null
  test_name: string | null
  follow_up_date: string | null
  report_date: string | null
  tags: string[]
  medicines: Medicine[]
  results: LabResult[]
}

export interface RecordSummary {
  id: string
  record_type: RecordType
  title: string
  record_date: string
  doctor_name: string | null
  lab_name: string | null
  hospital: string | null
  tags: string[]
  document_count: number
}

export interface RecordPage {
  items: RecordSummary[]
  total: number
  limit: number
  offset: number
}

export interface TagCount {
  name: string
  record_count: number
}

export interface TimelineItem {
  id: string
  record_type: RecordType
  title: string
  record_date: string
  doctor_name: string | null
  lab_name: string | null
  document_count: number
}

export interface RecordFilters {
  q: string
  types: RecordType[]
  tags: string[]
  dateFrom: string
  dateTo: string
}
