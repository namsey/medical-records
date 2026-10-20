import { Camera, FileText, Image as ImageIcon, Paperclip, X } from 'lucide-react'
import { useRef, useState, type ChangeEvent } from 'react'
import { useAppConfig, useStorageUse } from '@/hooks/queries'
import { formatFileSize } from '@/lib/format'
import { Button } from '../ui/Button'
import { Field } from '../ui/Field'

const ACCEPT = '.pdf,.jpg,.jpeg,.png,.heic,.heif,application/pdf,image/jpeg,image/png,image/heic,image/heif'
const FALLBACK_EXTENSIONS = ['.pdf', '.jpg', '.jpeg', '.png', '.heic', '.heif']

/** Returns a message if the file cannot be uploaded, otherwise null. The server checks everything again. */
export function checkFile(file: File, maxMb: number, extensions: string[], spaceLeft = Infinity): string | null {
  const dot = file.name.lastIndexOf('.')
  const extension = dot >= 0 ? file.name.slice(dot).toLowerCase() : ''
  if (extension && !extensions.includes(extension)) return `${file.name}: only PDF, JPG, PNG and HEIC files are allowed.`
  if (file.size === 0) return `${file.name}: the file is empty.`
  if (file.size > maxMb * 1024 * 1024) return `${file.name}: larger than ${maxMb} MB.`
  if (file.size > spaceLeft) return `${file.name}: not enough storage left (${formatFileSize(Math.max(spaceLeft, 0))} free).`
  return null
}

/**
 * Copy a chosen file into memory. On Android a picked file (from Drive, WhatsApp, Downloads...) is only a
 * handle that can stop working before the upload starts, and the upload then fails as if the server were
 * unreachable. Reading it right away keeps it safe, and a file the phone cannot read is reported now.
 */
export async function readIntoMemory(file: File): Promise<File> {
  const bytes = await file.arrayBuffer()
  return new File([bytes], file.name, { type: file.type, lastModified: file.lastModified })
}

interface FilePickerProps {
  files: File[]
  onChange: (files: File[]) => void
  label?: string
  disabled?: boolean
}

/** Chooses files from the phone (gallery / files app) or straight from the camera. */
export function FilePicker({ files, onChange, label = 'Attachments', disabled }: FilePickerProps) {
  const { data: config } = useAppConfig()
  const maxMb = config?.max_upload_mb ?? 20
  const extensions = config?.allowed_extensions ?? FALLBACK_EXTENSIONS
  const { data: storage } = useStorageUse()
  const filesInput = useRef<HTMLInputElement>(null)
  const cameraInput = useRef<HTMLInputElement>(null)
  const [problems, setProblems] = useState<string[]>([])

  async function accept(event: ChangeEvent<HTMLInputElement>) {
    const chosen = Array.from(event.target.files ?? [])
    event.target.value = '' // allow choosing the same file again later
    const rejected: string[] = []
    // Space left after the files already chosen for this record.
    let spaceLeft = storage ? storage.quota_bytes - storage.used_bytes - files.reduce((sum, file) => sum + file.size, 0) : Infinity
    const checked = chosen.filter((file) => {
      const problem = checkFile(file, maxMb, extensions, spaceLeft)
      if (problem) rejected.push(problem)
      else spaceLeft -= file.size
      return !problem
    })
    const accepted: File[] = []
    for (const file of checked) {
      try {
        accepted.push(await readIntoMemory(file))
      } catch {
        rejected.push(`${file.name}: the phone could not open this file. If it is in Google Drive or another app, save it to the phone first and choose it again.`)
      }
    }
    setProblems(rejected)
    if (accepted.length) onChange([...files, ...accepted])
  }

  return (
    <Field label={label} hint={`PDF, JPG, PNG or HEIC (iPhone photos), up to ${maxMb} MB each.`}>
      <div className="space-y-3">
        <div className="grid grid-cols-2 gap-3">
          <Button variant="secondary" disabled={disabled} onClick={() => filesInput.current?.click()}>
            <Paperclip className="size-5" aria-hidden />
            Choose files
          </Button>
          <Button variant="secondary" disabled={disabled} onClick={() => cameraInput.current?.click()}>
            <Camera className="size-5" aria-hidden />
            Take photo
          </Button>
        </div>
        <input ref={filesInput} type="file" multiple accept={ACCEPT} onChange={accept} className="hidden" tabIndex={-1} aria-hidden />
        <input ref={cameraInput} type="file" accept="image/*" capture="environment" onChange={accept} className="hidden" tabIndex={-1} aria-hidden />

        {problems.length > 0 && (
          <p role="alert" className="whitespace-pre-line rounded-xl bg-danger-50 p-3 text-sm text-danger-700">
            {problems.join('\n')}
          </p>
        )}

        {files.length > 0 && (
          <ul className="space-y-2">
            {files.map((file, index) => (
              <li key={`${file.name}-${index}`} className="flex items-center gap-3 rounded-xl border border-line bg-white px-3 py-2">
                {file.type === 'application/pdf' ? <FileText className="size-5 shrink-0 text-rose-700" aria-hidden /> : <ImageIcon className="size-5 shrink-0 text-indigo-700" aria-hidden />}
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium">{file.name}</p>
                  <p className="text-xs text-muted">{formatFileSize(file.size)}</p>
                </div>
                <button type="button" disabled={disabled} onClick={() => onChange(files.filter((_, i) => i !== index))} aria-label={`Remove ${file.name}`} className="grid size-11 place-items-center rounded-full text-muted hover:bg-wash">
                  <X className="size-5" />
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </Field>
  )
}
