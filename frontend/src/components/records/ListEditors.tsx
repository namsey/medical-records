import { Plus, Trash2 } from 'lucide-react'
import { emptyMedicine, emptyResult, type MedicineForm, type ResultForm } from '@/lib/recordForm'
import { FLAG_OPTIONS } from '@/lib/recordTypes'
import { Button } from '../ui/Button'
import { SelectInput, TextArea, TextInput } from '../ui/Field'

interface MedicinesEditorProps {
  medicines: MedicineForm[]
  errors: Record<string, string>
  onChange: (next: MedicineForm[]) => void
}

export function MedicinesEditor({ medicines, errors, onChange }: MedicinesEditorProps) {
  const update = (key: string, patch: Partial<MedicineForm>) => onChange(medicines.map((m) => (m.key === key ? { ...m, ...patch } : m)))

  return (
    <div className="space-y-3">
      <h2 className="section-heading">Medicines</h2>
      {medicines.length === 0 && <p className="text-sm text-muted">No medicines added yet.</p>}
      {medicines.map((medicine, index) => (
        <div key={medicine.key} className="space-y-3 rounded-xl border border-line bg-paper p-3">
          <div className="flex items-center justify-between">
            <p className="text-sm font-semibold text-muted">Medicine {index + 1}</p>
            <button type="button" onClick={() => onChange(medicines.filter((m) => m.key !== medicine.key))} aria-label={`Remove medicine ${index + 1}`} className="grid size-11 place-items-center rounded-full text-danger-700 hover:bg-danger-50">
              <Trash2 className="size-5" />
            </button>
          </div>
          <TextInput label="Name" value={medicine.name} onChange={(e) => update(medicine.key, { name: e.target.value })} maxLength={255} error={errors[`medicine-${medicine.key}`]} placeholder="e.g. Paracetamol" />
          <div className="grid grid-cols-2 gap-3">
            <TextInput label="Dosage" value={medicine.dosage} onChange={(e) => update(medicine.key, { dosage: e.target.value })} maxLength={255} placeholder="500 mg" />
            <TextInput label="Frequency" value={medicine.frequency} onChange={(e) => update(medicine.key, { frequency: e.target.value })} maxLength={255} placeholder="Twice a day" />
          </div>
          <TextInput label="Duration" value={medicine.duration} onChange={(e) => update(medicine.key, { duration: e.target.value })} maxLength={255} placeholder="5 days" />
          <div className="grid grid-cols-2 gap-3">
            <TextInput label="Start date" type="date" value={medicine.startDate} onChange={(e) => update(medicine.key, { startDate: e.target.value })} />
            <TextInput label="End date" type="date" value={medicine.endDate} min={medicine.startDate || undefined} onChange={(e) => update(medicine.key, { endDate: e.target.value })} />
          </div>
          <TextArea label="Instructions" rows={2} value={medicine.instructions} onChange={(e) => update(medicine.key, { instructions: e.target.value })} maxLength={10000} placeholder="After food" />
        </div>
      ))}
      <Button variant="secondary" className="w-full" onClick={() => onChange([...medicines, emptyMedicine()])}>
        <Plus className="size-5" aria-hidden />
        Add medicine
      </Button>
    </div>
  )
}

interface ResultsEditorProps {
  results: ResultForm[]
  errors: Record<string, string>
  onChange: (next: ResultForm[]) => void
}

export function LabResultsEditor({ results, errors, onChange }: ResultsEditorProps) {
  const update = (key: string, patch: Partial<ResultForm>) => onChange(results.map((r) => (r.key === key ? { ...r, ...patch } : r)))

  return (
    <div className="space-y-3">
      <div>
        <h2 className="section-heading">Individual results</h2>
        <p className="text-sm text-muted">Optional. Enter values exactly as printed on the report.</p>
      </div>
      {results.map((result, index) => (
        <div key={result.key} className="space-y-3 rounded-xl border border-line bg-paper p-3">
          <div className="flex items-center justify-between">
            <p className="text-sm font-semibold text-muted">Result {index + 1}</p>
            <button type="button" onClick={() => onChange(results.filter((r) => r.key !== result.key))} aria-label={`Remove result ${index + 1}`} className="grid size-11 place-items-center rounded-full text-danger-700 hover:bg-danger-50">
              <Trash2 className="size-5" />
            </button>
          </div>
          <TextInput label="Parameter" value={result.parameter} onChange={(e) => update(result.key, { parameter: e.target.value })} maxLength={255} error={errors[`result-${result.key}`]} placeholder="Vitamin B12" />
          <div className="grid grid-cols-2 gap-3">
            <TextInput label="Value" value={result.value} onChange={(e) => update(result.key, { value: e.target.value })} maxLength={100} placeholder="296" />
            <TextInput label="Unit" value={result.unit} onChange={(e) => update(result.key, { unit: e.target.value })} maxLength={50} placeholder="pg/mL" />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <TextInput label="Reference range" value={result.referenceRange} onChange={(e) => update(result.key, { referenceRange: e.target.value })} maxLength={100} placeholder="200-900" />
            <SelectInput label="Flag" value={result.flag} onChange={(e) => update(result.key, { flag: e.target.value })}>
              <option value="">None</option>
              {FLAG_OPTIONS.map((flag) => (
                <option key={flag} value={flag}>
                  {flag}
                </option>
              ))}
            </SelectInput>
          </div>
        </div>
      ))}
      <Button variant="secondary" className="w-full" onClick={() => onChange([...results, emptyResult()])}>
        <Plus className="size-5" aria-hidden />
        Add result
      </Button>
    </div>
  )
}
