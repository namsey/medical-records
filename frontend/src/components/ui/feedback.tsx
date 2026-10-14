import { AlertCircle, Loader2, type LucideIcon } from 'lucide-react'
import type { ReactNode } from 'react'
import { Button } from './Button'

export function Spinner({ className = 'size-5' }: { className?: string }) {
  return <Loader2 className={`animate-spin text-brand-600 ${className}`} aria-hidden />
}

export function LoadingState({ label = 'Loading…' }: { label?: string }) {
  return (
    <div role="status" className="flex flex-col items-center justify-center gap-3 py-16 text-muted">
      <Spinner className="size-7" />
      <span className="text-sm">{label}</span>
    </div>
  )
}

/** Placeholder cards shown while a list is loading. */
export function CardSkeletons({ count = 4 }: { count?: number }) {
  return (
    <div role="status" aria-label="Loading" className="space-y-3">
      {Array.from({ length: count }, (_, index) => (
        <div key={index} className="card flex animate-pulse items-center gap-3 p-4">
          <div className="size-11 rounded-xl bg-wash" />
          <div className="flex-1 space-y-2">
            <div className="h-4 w-2/3 rounded bg-wash" />
            <div className="h-3 w-1/3 rounded bg-wash" />
          </div>
        </div>
      ))}
    </div>
  )
}

interface EmptyStateProps {
  icon: LucideIcon
  title: string
  description?: string
  action?: ReactNode
}

export function EmptyState({ icon: Icon, title, description, action }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center px-6 py-14 text-center">
      <div className="mb-4 grid size-16 place-items-center rounded-full bg-brand-50 text-brand-700">
        <Icon className="size-8" aria-hidden />
      </div>
      <h2 className="section-heading">{title}</h2>
      {description && <p className="mt-1 max-w-xs text-sm text-muted">{description}</p>}
      {action && <div className="mt-5">{action}</div>}
    </div>
  )
}

interface ErrorMessageProps {
  message: string
  onRetry?: () => void
  className?: string
}

export function ErrorMessage({ message, onRetry, className = '' }: ErrorMessageProps) {
  return (
    <div role="alert" className={`flex items-start gap-3 rounded-xl border border-danger-600/25 bg-danger-50 p-4 text-sm text-danger-700 ${className}`}>
      <AlertCircle className="mt-0.5 size-5 shrink-0" aria-hidden />
      <div className="flex-1 whitespace-pre-line">{message}</div>
      {onRetry && (
        <Button variant="secondary" size="sm" onClick={onRetry}>
          Retry
        </Button>
      )}
    </div>
  )
}
