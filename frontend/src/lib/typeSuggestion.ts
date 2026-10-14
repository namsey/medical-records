import type { RecordType } from './types'

/**
 * Title keywords that hint at a record type, checked in this order (so "Body checkup" is a lab report,
 * not a doctor visit). Only ever used as a dismissible suggestion.
 */
const KEYWORDS: [RecordType, RegExp][] = [
  ['scan', /\b(ultrasound|usg|sonograph\w*|mri|ct|cat scan|pet scan|x-?ray|x ray|mammogra\w*|doppler|echocardiogra\w*|scan)\b/i],
  ['lab_report', /\b(cbc|complete blood count|blood (test|work|report|sugar)|lipid\w*|tsh|thyroid (profile|panel|test)|hba1c|vitamin|urine|glucose|lft|kft|liver function|kidney function|culture|ha?emoglobin|body check-?up|lab)\b/i],
  ['prescription', /\b(prescription|rx|medicines?|medication)\b/i],
  ['diagnosis', /\b(diagnos\w*)\b/i],
  ['medical_document', /\b(discharge|certificate|insurance|referral)\b/i],
  ['doctor_visit', /\b(consult\w*|check-?up|visit|follow-?up|opd|appointment)\b/i],
]

/** Suggest a record type from a title, or null when nothing matches. */
export function suggestRecordType(title: string): RecordType | null {
  const text = title.trim()
  if (!text) return null
  return KEYWORDS.find(([, pattern]) => pattern.test(text))?.[0] ?? null
}
