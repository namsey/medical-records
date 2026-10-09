import { Navigate, Outlet, useLocation } from 'react-router-dom'
import { useMe } from '@/hooks/queries'
import { LoadingState } from '../ui/feedback'
import { BottomNav } from './BottomNav'

/** Wraps every private page: requires a login, then shows the page above the bottom navigation. */
export function AppLayout() {
  const { data: user, isPending, isError, refetch } = useMe()
  const location = useLocation()

  if (isPending) return <LoadingState label="Signing in…" />
  if (isError) {
    return (
      <div className="mx-auto max-w-md p-6 text-center">
        <p className="mb-4 text-muted">Could not reach the server.</p>
        <button type="button" onClick={() => void refetch()} className="min-h-12 rounded-xl bg-brand-700 px-5 font-semibold text-white">
          Try again
        </button>
      </div>
    )
  }
  if (!user) return <Navigate to="/login" replace state={{ from: location.pathname }} />

  return (
    <div className="min-h-dvh">
      <main className="mx-auto w-full max-w-2xl px-4 pb-28 pt-2">
        <Outlet />
      </main>
      <BottomNav />
    </div>
  )
}
