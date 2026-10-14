import { ArrowLeft, X } from 'lucide-react'
import type { ReactNode } from 'react'
import { Link, useNavigate } from 'react-router-dom'

interface PageHeaderProps {
  title: string
  subtitle?: string
  /** `true` goes back in history; a string links to that path. */
  back?: boolean | string
  /** Handles the back control itself (e.g. to confirm discarding changes); takes precedence over `back`. */
  onBack?: () => void
  /** Show the back control as a close (X) button. */
  backIcon?: 'arrow' | 'close'
  action?: ReactNode
}

export function PageHeader({ title, subtitle, back, onBack, backIcon = 'arrow', action }: PageHeaderProps) {
  const navigate = useNavigate()
  const backClasses = '-ml-2 grid size-11 shrink-0 place-items-center rounded-full text-ink hover:bg-wash'
  const BackIcon = backIcon === 'close' ? X : ArrowLeft
  const backLabel = backIcon === 'close' ? 'Close' : 'Back'
  return (
    <header className="sticky top-0 z-30 -mx-4 mb-3 flex items-center gap-1 bg-paper/95 px-4 py-2 backdrop-blur">
      {(onBack || back === true) && (
        <button type="button" onClick={onBack ?? (() => navigate(-1))} aria-label={backLabel} className={backClasses}>
          <BackIcon className="size-6" />
        </button>
      )}
      {!onBack && typeof back === 'string' && (
        <Link to={back} aria-label={backLabel} className={backClasses}>
          <BackIcon className="size-6" />
        </Link>
      )}
      <div className="min-w-0 flex-1">
        <h1 className="page-title truncate">{title}</h1>
        {subtitle && <p className="page-subtitle truncate">{subtitle}</p>}
      </div>
      {action && <div className="flex shrink-0 items-center gap-1">{action}</div>}
    </header>
  )
}
