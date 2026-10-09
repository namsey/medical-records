import { ArrowLeft } from 'lucide-react'
import type { ReactNode } from 'react'
import { Link, useNavigate } from 'react-router-dom'

interface PageHeaderProps {
  title: string
  subtitle?: string
  /** `true` goes back in history; a string links to that path. */
  back?: boolean | string
  action?: ReactNode
}

export function PageHeader({ title, subtitle, back, action }: PageHeaderProps) {
  const navigate = useNavigate()
  const backClasses = '-ml-2 grid size-11 shrink-0 place-items-center rounded-full text-ink hover:bg-wash'
  return (
    <header className="sticky top-0 z-30 -mx-4 mb-3 flex items-center gap-1 bg-paper/95 px-4 py-2 backdrop-blur">
      {back === true && (
        <button type="button" onClick={() => navigate(-1)} aria-label="Back" className={backClasses}>
          <ArrowLeft className="size-6" />
        </button>
      )}
      {typeof back === 'string' && (
        <Link to={back} aria-label="Back" className={backClasses}>
          <ArrowLeft className="size-6" />
        </Link>
      )}
      <div className="min-w-0 flex-1">
        <h1 className="truncate text-2xl font-semibold leading-tight">{title}</h1>
        {subtitle && <p className="truncate text-sm text-muted">{subtitle}</p>}
      </div>
      {action && <div className="flex shrink-0 items-center gap-1">{action}</div>}
    </header>
  )
}
