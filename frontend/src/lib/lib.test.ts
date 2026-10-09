import { describe, expect, it, vi } from 'vitest'
import { ApiError, request } from './api'
import { formatDate, formatDayMonth, formatFileSize, orNull, pluralize, todayIso } from './format'
import { FORM_CONFIG, emptyForm, emptyMedicine, formFromRecord, formToInput, validateForm } from './recordForm'
import type { MedicalRecord } from './types'

describe('format', () => {
  it('formats dates as local calendar dates without timezone drift', () => {
    expect(formatDate('2026-09-05')).toBe('05 Sep 2026')
    expect(formatDate('2026-01-01T23:30:00Z')).toBe('01 Jan 2026')
    expect(formatDayMonth('2026-12-31')).toBe('31 Dec')
    expect(formatDate(null)).toBe('')
  })

  it('formats file sizes', () => {
    expect(formatFileSize(512)).toBe('512 B')
    expect(formatFileSize(2048)).toBe('2 KB')
    expect(formatFileSize(5 * 1024 * 1024)).toBe('5.0 MB')
  })

  it('trims blanks to null and pluralizes', () => {
    expect(orNull('  ')).toBeNull()
    expect(orNull(' hi ')).toBe('hi')
    expect(pluralize(1, 'record')).toBe('1 record')
    expect(pluralize(3, 'record')).toBe('3 records')
  })

  it('returns today as an ISO date', () => {
    expect(todayIso()).toMatch(/^\d{4}-\d{2}-\d{2}$/)
  })
})

describe('record form', () => {
  it('sends only the fields the record type uses', () => {
    const form = emptyForm('doctor_visit')
    form.reason = ' Chest pain '
    form.hospital = 'City Hospital'
    form.testName = 'should be ignored'
    form.summary = 'also ignored'
    form.personalNotes = 'Felt ok'
    form.tags = ['Heart']
    const input = formToInput(form)
    expect(input.reason).toBe('Chest pain')
    expect(input.hospital).toBe('City Hospital')
    expect(input.test_name).toBeNull()
    expect(input.summary).toBeNull()
    expect(input.personal_notes).toBe('Felt ok')
    expect(input.tags).toEqual(['Heart'])
    expect(input.medicines).toEqual([])
    expect(input.title).toBeNull()
  })

  it('drops blank medicines and keeps filled ones', () => {
    const form = emptyForm('prescription')
    const second = emptyMedicine()
    second.name = 'Paracetamol'
    second.dosage = '500 mg'
    second.startDate = '2026-09-05'
    form.medicines = [...form.medicines, second]
    const input = formToInput(form)
    expect(input.medicines).toHaveLength(1)
    expect(input.medicines[0]).toMatchObject({ name: 'Paracetamol', dosage: '500 mg', start_date: '2026-09-05', end_date: null })
  })

  it('validates required fields per record type', () => {
    expect(validateForm(emptyForm('doctor_visit'))).toEqual({})
    expect(validateForm(emptyForm('scan'))).toHaveProperty('title')
    expect(validateForm(emptyForm('lab_report'))).toHaveProperty('testName')
    expect(validateForm(emptyForm('diagnosis'))).toHaveProperty('diagnosis')
    const noDate = emptyForm('doctor_visit')
    noDate.recordDate = ''
    expect(validateForm(noDate)).toHaveProperty('recordDate')
  })

  it('flags half-filled medicines and impossible date ranges', () => {
    const form = emptyForm('prescription')
    const medicine = form.medicines[0]!
    medicine.dosage = '10 mg'
    expect(Object.values(validateForm(form))).toContain('Enter the medicine name')
    medicine.name = 'X'
    medicine.startDate = '2026-02-01'
    medicine.endDate = '2026-01-01'
    expect(Object.values(validateForm(form))).toContain('End date is before the start date')
  })

  it('round-trips a stored record through the form', () => {
    const record = {
      id: 'r1', record_type: 'lab_report', title: 'T', record_date: '2026-09-10', doctor_id: 'd1', lab_id: 'l1',
      hospital: null, specialization: null, reason: 'Routine', symptoms: null, diagnosis: null, description: null,
      treatment: null, doctor_notes: null, summary: 'ok', personal_notes: null, test_name: 'B12',
      follow_up_date: null, report_date: '2026-09-11', tags: ['Blood'], medicines: [],
      results: [{ parameter: 'B12', value: '296', unit: 'pg/mL', reference_range: '200-900', flag: 'Normal' }],
    } as unknown as MedicalRecord
    const input = formToInput(formFromRecord(record))
    expect(input).toMatchObject({
      record_type: 'lab_report', record_date: '2026-09-10', doctor_id: 'd1', lab_id: 'l1', test_name: 'B12',
      report_date: '2026-09-11', summary: 'ok', reason: 'Routine', tags: ['Blood'],
    })
    expect(input.results[0]).toEqual({ parameter: 'B12', value: '296', unit: 'pg/mL', reference_range: '200-900', flag: 'Normal' })
  })

  it('has a config for every record type', () => {
    for (const type of ['doctor_visit', 'prescription', 'lab_report', 'diagnosis', 'medical_document', 'scan', 'other'] as const) {
      expect(FORM_CONFIG[type].dateLabel).toBeTruthy()
    }
  })
})

describe('api client', () => {
  it('sends the CSRF header and parses JSON', async () => {
    const fetchMock = vi.fn(async () => new Response(JSON.stringify({ ok: true }), { status: 200 }))
    vi.stubGlobal('fetch', fetchMock)
    await expect(request('/api/doctors', { method: 'POST', json: { name: 'x' } })).resolves.toEqual({ ok: true })
    const init = (fetchMock.mock.calls[0] as unknown as [string, RequestInit])[1]
    expect((init.headers as Record<string, string>)['X-Requested-With']).toBe('XMLHttpRequest')
    expect((init.headers as Record<string, string>)['Content-Type']).toBe('application/json')
    vi.unstubAllGlobals()
  })

  it('turns FastAPI validation errors into readable messages', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => new Response(JSON.stringify({ detail: [{ loc: ['body', 'test_name'], msg: 'Value error, Test name is required' }] }), { status: 422 })),
    )
    await expect(request('/api/records', { method: 'POST', json: {} })).rejects.toMatchObject({ status: 422, message: 'test name: Test name is required' })
    vi.unstubAllGlobals()
  })

  it('reports plain error details and network failures', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({ detail: 'Record not found' }), { status: 404 })))
    await expect(request('/api/records/x')).rejects.toMatchObject({ status: 404, message: 'Record not found' })
    vi.stubGlobal('fetch', vi.fn(async () => { throw new TypeError('offline') }))
    const error = await request('/api/records').catch((e: unknown) => e)
    expect(error).toBeInstanceOf(ApiError)
    expect((error as ApiError).status).toBe(0)
    vi.unstubAllGlobals()
  })

  it('returns undefined for 204 responses', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(null, { status: 204 })))
    await expect(request('/api/records/x', { method: 'DELETE' })).resolves.toBeUndefined()
    vi.unstubAllGlobals()
  })
})
