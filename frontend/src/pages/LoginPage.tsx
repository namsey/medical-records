import { LogIn, ShieldCheck } from 'lucide-react'
import { Navigate, useSearchParams } from 'react-router-dom'
import { buttonClasses } from '@/components/ui/Button'
import { LoadingState } from '@/components/ui/feedback'
import { useMe } from '@/hooks/queries'

const MESSAGES: Record<string, string> = {
  not_allowed: 'That Google account is not allowed to use this app.',
  denied: 'Sign-in was cancelled.',
  failed: 'Sign-in did not work. Please try again.',
}

export function LoginPage() {
  const { data: user, isPending } = useMe()
  const [params] = useSearchParams()
  const error = params.get('error')

  if (isPending) return <LoadingState />
  if (user) return <Navigate to="/" replace />

  return (
    <main className="page-container flex min-h-dvh max-w-md flex-col justify-center py-10">
      <div className="mb-8 text-center">
        <div className="mx-auto mb-5 grid size-20 place-items-center rounded-3xl bg-brand-700 text-paper shadow-md">
          <svg viewBox="0 0 64 64" className="size-11" aria-hidden>
            <path d="M26 10h12v16h16v12H38v16H26V38H10V26h16z" fill="currentColor" />
          </svg>
        </div>
        <h1 className="page-title">Medical Records</h1>
        <p className="page-subtitle mt-2">Your private health journal: prescriptions, lab reports and visits in one place.</p>
      </div>

      {error && (
        <p role="alert" className="mb-4 rounded-xl border border-danger-600/25 bg-danger-50 p-3 text-center text-sm text-danger-700">
          {MESSAGES[error] ?? MESSAGES.failed}
        </p>
      )}

      {/* A normal link: Google sign-in needs a full-page navigation, not a fetch call. */}
      <a href="/api/auth/login" className={buttonClasses('primary', 'md', 'w-full text-lg')}>
        <LogIn className="size-5" aria-hidden />
        Sign in with Google
      </a>

      <p className="mt-6 flex items-center justify-center gap-2 text-center text-sm text-muted">
        <ShieldCheck className="size-4 shrink-0" aria-hidden />
        Only the owner's Google account can open this app.
      </p>
    </main>
  )
}
