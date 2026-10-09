import { Link } from 'react-router-dom'
import { formatDate } from '@/lib/format'
import { FORM_CONFIG, fieldLabel, type FieldKey } from '@/lib/recordForm'
import { flagTone } from '@/lib/recordTypes'
import type { LabResult, MedicalRecord, Medicine } from '@/lib/types'
import { TagPill } from '../ui/Chip'

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <dt className="text-xs font-semibold uppercase tracking-wide text-muted">{label}</dt>
      <dd className="mt-0.5 whitespace-pre-line break-words text-base leading-relaxed">{children}</dd>
    </div>
  )
}

const TEXT_FIELDS: Record<Exclude<FieldKey, 'title' | 'doctor' | 'lab'>, (record: MedicalRecord) => string | null> = {
  testName: (r) => r.test_name,
  reportDate: (r) => (r.report_date ? formatDate(r.report_date) : null),
  hospital: (r) => r.hospital,
  specialization: (r) => r.specialization,
  reason: (r) => r.reason,
  symptoms: (r) => r.symptoms,
  diagnosis: (r) => r.diagnosis,
  description: (r) => r.description,
  treatment: (r) => r.treatment,
  doctorNotes: (r) => r.doctor_notes,
  summary: (r) => r.summary,
  followUpDate: (r) => (r.follow_up_date ? formatDate(r.follow_up_date) : null),
}

/** The key facts of a record, using the same labels as the form. Empty fields are left out. */
export function RecordFacts({ record }: { record: MedicalRecord }) {
  const config = FORM_CONFIG[record.record_type]
  const doctorLine = record.doctor ? [record.doctor.name, record.doctor.specialization].filter(Boolean).join(' · ') : null

  return (
    <dl className="card space-y-4 p-4">
      <Row label={config.dateLabel}>{formatDate(record.record_date)}</Row>
      {config.fields.map((field) => {
        if (field === 'title') return null
        const label = fieldLabel(record.record_type, field)
        if (field === 'doctor') return doctorLine ? <Row key={field} label={label}>{doctorLine}</Row> : null
        if (field === 'lab') return record.lab ? <Row key={field} label={label}>{record.lab.name}</Row> : null
        const value = TEXT_FIELDS[field](record)
        return value ? (
          <Row key={field} label={label}>
            {value}
          </Row>
        ) : null
      })}
    </dl>
  )
}

function MedicineCard({ medicine }: { medicine: Medicine }) {
  const schedule = [medicine.dosage, medicine.frequency, medicine.duration].filter(Boolean).join(' · ')
  const dates = [medicine.start_date && `from ${formatDate(medicine.start_date)}`, medicine.end_date && `until ${formatDate(medicine.end_date)}`].filter(Boolean).join(' ')
  return (
    <li className="card p-4">
      <p className="font-semibold">{medicine.name}</p>
      {schedule && <p className="text-sm">{schedule}</p>}
      {dates && <p className="text-sm text-muted">{dates}</p>}
      {medicine.instructions && <p className="mt-1 whitespace-pre-line text-sm text-muted">{medicine.instructions}</p>}
    </li>
  )
}

export function MedicineList({ medicines }: { medicines: Medicine[] }) {
  if (medicines.length === 0) return null
  return (
    <section className="space-y-2">
      <h2 className="text-lg font-semibold">Medicines</h2>
      <ul className="space-y-2">
        {medicines.map((medicine, index) => (
          <MedicineCard key={medicine.id ?? index} medicine={medicine} />
        ))}
      </ul>
    </section>
  )
}

function ResultCard({ result }: { result: LabResult }) {
  const measured = [result.value, result.unit].filter(Boolean).join(' ')
  return (
    <li className="card flex items-start justify-between gap-3 p-4">
      <div className="min-w-0">
        <p className="font-semibold">{result.parameter}</p>
        {result.reference_range && <p className="text-sm text-muted">Reference: {result.reference_range}</p>}
      </div>
      <div className="shrink-0 text-right">
        {measured && <p className="text-lg font-semibold">{measured}</p>}
        {result.flag && <span className={`mt-1 inline-block rounded-full px-2.5 py-0.5 text-xs font-semibold ${flagTone(result.flag)}`}>{result.flag}</span>}
      </div>
    </li>
  )
}

export function ResultList({ results }: { results: LabResult[] }) {
  if (results.length === 0) return null
  return (
    <section className="space-y-2">
      <h2 className="text-lg font-semibold">Results</h2>
      <ul className="space-y-2">
        {results.map((result, index) => (
          <ResultCard key={result.id ?? index} result={result} />
        ))}
      </ul>
    </section>
  )
}

export function TagLinks({ tags }: { tags: string[] }) {
  if (tags.length === 0) return null
  return (
    <div className="flex flex-wrap gap-2">
      {tags.map((tag) => (
        <Link key={tag} to={`/records?tag=${encodeURIComponent(tag)}`}>
          <TagPill>{tag}</TagPill>
        </Link>
      ))}
    </div>
  )
}
