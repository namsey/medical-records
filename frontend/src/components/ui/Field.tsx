import { useId, type InputHTMLAttributes, type ReactNode, type SelectHTMLAttributes, type TextareaHTMLAttributes } from 'react'

interface FieldProps {
  label: string
  hint?: string
  required?: boolean
  error?: string | null
  htmlFor?: string
  children: ReactNode
}

export function Field({ label, hint, required, error, htmlFor, children }: FieldProps) {
  return (
    <div className="space-y-1.5">
      <label htmlFor={htmlFor} className="block text-sm font-semibold text-ink">
        {label}
        {required && <span className="text-danger-600"> *</span>}
      </label>
      {children}
      {hint && !error && <p className="text-xs text-muted">{hint}</p>}
      {error && (
        <p role="alert" className="text-xs font-medium text-danger-700">
          {error}
        </p>
      )}
    </div>
  )
}

interface CommonProps {
  label: string
  hint?: string
  error?: string | null
}

export function TextInput({ label, hint, error, required, className = '', ...rest }: CommonProps & InputHTMLAttributes<HTMLInputElement>) {
  const id = useId()
  return (
    <Field label={label} hint={hint} error={error} required={required} htmlFor={id}>
      <input id={id} required={required} className={`field-input ${className}`} aria-invalid={Boolean(error)} {...rest} />
    </Field>
  )
}

export function TextArea({ label, hint, error, required, rows = 3, className = '', ...rest }: CommonProps & TextareaHTMLAttributes<HTMLTextAreaElement>) {
  const id = useId()
  return (
    <Field label={label} hint={hint} error={error} required={required} htmlFor={id}>
      <textarea id={id} rows={rows} required={required} className={`field-input resize-y leading-relaxed ${className}`} aria-invalid={Boolean(error)} {...rest} />
    </Field>
  )
}

export function SelectInput({ label, hint, error, required, className = '', children, ...rest }: CommonProps & SelectHTMLAttributes<HTMLSelectElement>) {
  const id = useId()
  return (
    <Field label={label} hint={hint} error={error} required={required} htmlFor={id}>
      <select id={id} required={required} className={`field-input appearance-auto ${className}`} {...rest}>
        {children}
      </select>
    </Field>
  )
}

/** A titled group of related fields inside a form. */
export function FormSection({ title, children }: { title?: string; children: ReactNode }) {
  return (
    <section className="card space-y-4 p-4">
      {title && <h2 className="text-lg font-semibold">{title}</h2>}
      {children}
    </section>
  )
}
