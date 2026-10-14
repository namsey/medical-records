import { CircleUserRound, FolderOpen, House, Plus, Search, type LucideIcon } from 'lucide-react'
import { Link, useLocation } from 'react-router-dom'

interface NavItem {
  to: string
  label: string
  icon: LucideIcon
  isActive: (path: string) => boolean
  prominent?: boolean
}

const ITEMS: NavItem[] = [
  { to: '/', label: 'Home', icon: House, isActive: (path) => path === '/' },
  {
    to: '/records',
    label: 'Records',
    icon: FolderOpen,
    isActive: (path) => path.startsWith('/records') || path.startsWith('/timeline') || path.startsWith('/documents'),
  },
  { to: '/add', label: 'Add', icon: Plus, isActive: (path) => path.startsWith('/add'), prominent: true },
  { to: '/search', label: 'Search', icon: Search, isActive: (path) => path.startsWith('/search') },
  {
    to: '/profile',
    label: 'Profile',
    icon: CircleUserRound,
    isActive: (path) => ['/profile', '/more', '/doctors', '/labs'].some((prefix) => path.startsWith(prefix)),
  },
]

export function BottomNav() {
  const { pathname } = useLocation()
  return (
    <nav aria-label="Main" className="pb-safe fixed inset-x-0 bottom-0 z-40 h-[calc(var(--bottom-nav-height)+env(safe-area-inset-bottom))] border-t border-line bg-paper/95 backdrop-blur">
      <ul className="mx-auto flex h-full max-w-2xl items-stretch justify-around px-2">
        {ITEMS.map(({ to, label, icon: Icon, isActive, prominent }) => {
          const active = isActive(pathname)
          return (
            <li key={to} className="flex flex-1">
              <Link
                to={to}
                aria-current={active ? 'page' : undefined}
                className={`flex flex-1 flex-col items-center justify-center gap-0.5 text-xs font-semibold transition ${
                  active ? 'text-brand-700' : 'text-muted hover:text-ink'
                }`}
              >
                {prominent ? (
                  <span className="grid size-10 place-items-center rounded-full bg-brand-700 text-white shadow-sm">
                    <Icon className="size-6" aria-hidden />
                  </span>
                ) : (
                  <Icon className="size-6" strokeWidth={active ? 2.5 : 2} aria-hidden />
                )}
                {label}
              </Link>
            </li>
          )
        })}
      </ul>
    </nav>
  )
}
