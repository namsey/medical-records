import { Check, LogOut } from 'lucide-react'
import { PrivacyNotice } from '@/components/privacy/PrivacyNotice'
import { Button } from '@/components/ui/Button'
import { useGiveConsent, useLogout, usePrivacyInfo } from '@/hooks/queries'
import { errorMessage } from '@/lib/api'

/** Shown after sign-in until the current privacy notice is accepted. The server refuses records until then too. */
export function ConsentPage() {
  const { data: info } = usePrivacyInfo()
  const consent = useGiveConsent()
  const logout = useLogout()

  return (
    <main className="page-container max-w-2xl space-y-6 py-8">
      <div>
        <h1 className="page-title">Before you start</h1>
        <p className="page-subtitle mt-2">Please read how your health records are kept. You only need to do this once.</p>
      </div>
      <div className="card p-5">
        <PrivacyNotice />
      </div>
      {consent.isError && (
        <p role="alert" className="rounded-xl bg-danger-50 p-3 text-sm text-danger-700">
          {errorMessage(consent.error)}
        </p>
      )}
      <div className="grid gap-3 sm:grid-cols-2">
        <Button variant="secondary" loading={logout.isPending} onClick={() => logout.mutate()}>
          <LogOut className="size-5" aria-hidden />
          Sign out
        </Button>
        <Button disabled={!info} loading={consent.isPending} onClick={() => info && consent.mutate(info.version)}>
          <Check className="size-5" aria-hidden />I agree
        </Button>
      </div>
    </main>
  )
}
