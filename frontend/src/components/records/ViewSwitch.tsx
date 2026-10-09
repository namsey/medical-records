import { Link } from 'react-router-dom'

/** List / Timeline toggle shared by the two ways of browsing all records. */
export function ViewSwitch({ active }: { active: 'list' | 'timeline' }) {
  const base = 'flex min-h-11 flex-1 items-center justify-center rounded-lg text-sm font-semibold transition'
  const on = 'bg-white text-ink shadow-sm'
  const off = 'text-muted hover:text-ink'
  return (
    <div className="mb-3 flex rounded-xl bg-wash p-1" role="tablist" aria-label="Browse records as">
      <Link to="/records" role="tab" aria-selected={active === 'list'} className={`${base} ${active === 'list' ? on : off}`}>
        List
      </Link>
      <Link to="/timeline" role="tab" aria-selected={active === 'timeline'} className={`${base} ${active === 'timeline' ? on : off}`}>
        Timeline
      </Link>
    </div>
  )
}
