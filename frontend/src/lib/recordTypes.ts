import {
  Activity,
  FileText,
  FlaskConical,
  Pill,
  ScanLine,
  Shapes,
  Stethoscope,
  type LucideIcon,
} from 'lucide-react'
import type { RecordType } from './types'

interface RecordTypeInfo {
  label: string
  plural: string
  icon: LucideIcon
  /** Classes for the coloured badge / icon tile, from the --color-type-* tokens in index.css. */
  tone: string
  hint: string
}

export const RECORD_TYPES: RecordType[] = [
  'doctor_visit',
  'prescription',
  'lab_report',
  'diagnosis',
  'medical_document',
  'scan',
  'other',
]

export const RECORD_TYPE_INFO: Record<RecordType, RecordTypeInfo> = {
  doctor_visit: {
    label: 'Doctor Visit',
    plural: 'Doctor Visits',
    icon: Stethoscope,
    tone: 'bg-type-doctor-visit-soft text-type-doctor-visit',
    hint: 'Consultation, symptoms, notes',
  },
  prescription: {
    label: 'Prescription',
    plural: 'Prescriptions',
    icon: Pill,
    tone: 'bg-type-prescription-soft text-type-prescription',
    hint: 'Medicines and instructions',
  },
  lab_report: {
    label: 'Lab Report',
    plural: 'Lab Reports',
    icon: FlaskConical,
    tone: 'bg-type-lab-report-soft text-type-lab-report',
    hint: 'Blood tests and results',
  },
  diagnosis: {
    label: 'Diagnosis',
    plural: 'Diagnoses',
    icon: Activity,
    tone: 'bg-type-diagnosis-soft text-type-diagnosis',
    hint: 'A condition and its treatment',
  },
  medical_document: {
    label: 'Medical Document',
    plural: 'Medical Documents',
    icon: FileText,
    tone: 'bg-type-medical-document-soft text-type-medical-document',
    hint: 'Certificates, discharge summaries',
  },
  scan: {
    label: 'Scan',
    plural: 'Scans',
    icon: ScanLine,
    tone: 'bg-type-scan-soft text-type-scan',
    hint: 'MRI, CT, X-ray, ultrasound',
  },
  other: {
    label: 'Other',
    plural: 'Other',
    icon: Shapes,
    tone: 'bg-type-other-soft text-type-other',
    hint: 'Anything else',
  },
}

export const FLAG_OPTIONS = ['Normal', 'Low', 'High', 'Abnormal', 'Critical']

export function flagTone(flag: string | null): string {
  switch ((flag ?? '').toLowerCase()) {
    case 'normal':
      return 'bg-emerald-100 text-emerald-800'
    case 'low':
    case 'high':
      return 'bg-amber-100 text-amber-800'
    case 'abnormal':
    case 'critical':
      return 'bg-rose-100 text-rose-800'
    default:
      return 'bg-slate-100 text-slate-700'
  }
}
