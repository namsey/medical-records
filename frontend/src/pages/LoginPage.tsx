import { LogIn, ShieldCheck } from 'lucide-react'
import { Navigate, useSearchParams } from 'react-router-dom'
import { AuthShell } from '@/components/layout/AuthShell'
import { buttonClasses } from '@/components/ui/Button'
import { LoadingState } from '@/components/ui/feedback'
import { useMe } from '@/hooks/queries'

const MESSAGES: Record<string, string> = {
  not_invited: 'This Google account has no invite. Ask the person who runs this app to invite you.',
  invite_invalid: 'This invite link has expired, was already used or was revoked. Ask for a new one.',
  invite_wrong_account: 'This invite is for a different Google account. Sign in with the account the invite was sent to.',
  disabled: 'This account has been disabled.',
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
    <AuthShell subtitle="Your private health journal: prescriptions, lab reports and visits in one place.">
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
        Only invited Google accounts can open this app.
      </p>
    </AuthShell>
  )
}
