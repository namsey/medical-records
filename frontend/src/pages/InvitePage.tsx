import { LogIn, ShieldCheck } from 'lucide-react'
import { Link, Navigate, useParams } from 'react-router-dom'
import { AuthShell } from '@/components/layout/AuthShell'
import { buttonClasses } from '@/components/ui/Button'
import { ErrorMessage, LoadingState } from '@/components/ui/feedback'
import { useInviteCheck, useMe } from '@/hooks/queries'
import { errorMessage } from '@/lib/api'

/** Where an invite link lands: check it, then sign in with Google carrying the invite. */
export function InvitePage() {
  const { token } = useParams()
  const me = useMe()
  const check = useInviteCheck(token)

  if (me.isPending || check.isPending) return <LoadingState />
  if (me.data) return <Navigate to="/" replace />

  return (
    <AuthShell subtitle="You have been invited to keep your health records here: prescriptions, lab reports and visits in one place.">
      {check.isError && <ErrorMessage message={errorMessage(check.error)} onRetry={() => void check.refetch()} />}
      {check.data?.valid === false && (
        <div className="space-y-4 text-center">
          <p role="alert" className="rounded-xl border border-danger-600/25 bg-danger-50 p-3 text-sm text-danger-700">
            This invite link has expired, was already used or was revoked. Ask the person who invited you for a new one.
          </p>
          <Link to="/login" className="font-semibold text-brand-700">
            Already have an account? Sign in
          </Link>
        </div>
      )}
      {check.data?.valid && (
        <>
          {/* A normal link: Google sign-in needs a full-page navigation, not a fetch call. */}
          <a href={`/api/auth/login?invite=${encodeURIComponent(token ?? '')}`} className={buttonClasses('primary', 'md', 'w-full text-lg')}>
            <LogIn className="size-5" aria-hidden />
            Sign in with Google
          </a>
          <p className="mt-6 flex items-center justify-center gap-2 text-center text-sm text-muted">
            <ShieldCheck className="size-4 shrink-0" aria-hidden />
            Use the Google account this invite was sent to. The link works once.
          </p>
        </>
      )}
    </AuthShell>
  )
}
