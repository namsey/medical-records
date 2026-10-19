import { CalendarClock, ChevronRight, Database, FileJson, FlaskConical, LogOut, MonitorSmartphone, ShieldCheck, Stethoscope, Trash2, UsersRound, type LucideIcon } from 'lucide-react'
import { useCallback, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { PageHeader } from '@/components/layout/PageHeader'
import { Button } from '@/components/ui/Button'
import { TextInput } from '@/components/ui/Field'
import { ConfirmDialog, Modal } from '@/components/ui/Modal'
import { useDeleteMyAccount, useLogout, useLogoutAll, useMe, usePrivacyInfo, useStorageUse } from '@/hooks/queries'
import { errorMessage } from '@/lib/api'
import { formatFileSize } from '@/lib/format'

function MenuLink({ to, icon: Icon, title, hint }: { to: string; icon: LucideIcon; title: string; hint: string }) {
  return (
    <Link to={to} className="card flex min-h-16 items-center gap-4 p-4 transition active:bg-wash">
      <span className="grid size-11 shrink-0 place-items-center rounded-xl bg-brand-50 text-brand-700">
        <Icon className="size-5" aria-hidden />
      </span>
      <span className="min-w-0 flex-1">
        <span className="block font-semibold leading-snug">{title}</span>
        <span className="block text-sm text-muted">{hint}</span>
      </span>
      <ChevronRight className="size-5 text-muted" aria-hidden />
    </Link>
  )
}

function DownloadLink({ href, icon: Icon, title, hint }: { href: string; icon: LucideIcon; title: string; hint: string }) {
  return (
    <a href={href} download className="card flex min-h-16 items-center gap-4 p-4 transition active:bg-wash">
      <span className="grid size-11 shrink-0 place-items-center rounded-xl bg-amber-100 text-amber-800">
        <Icon className="size-5" aria-hidden />
      </span>
      <span className="min-w-0 flex-1">
        <span className="block font-semibold leading-snug">{title}</span>
        <span className="block text-sm text-muted">{hint}</span>
      </span>
    </a>
  )
}

function StorageBar() {
  const { data } = useStorageUse()
  if (!data) return null
  const percent = data.quota_bytes > 0 ? Math.min(100, Math.round((data.used_bytes / data.quota_bytes) * 100)) : 100
  const nearlyFull = percent >= 90
  return (
    <section className="card space-y-2 p-4" aria-labelledby="storage-heading">
      <div className="flex items-baseline justify-between gap-3">
        <h2 id="storage-heading" className="font-semibold">
          Storage
        </h2>
        <p className="text-sm text-muted">
          {formatFileSize(data.used_bytes)} of {formatFileSize(data.quota_bytes)} used
        </p>
      </div>
      <div
        role="progressbar"
        aria-label="Storage used"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={percent}
        className="h-2.5 overflow-hidden rounded-full bg-wash"
      >
        <div className={`h-full rounded-full ${nearlyFull ? 'bg-amber-600' : 'bg-brand-700'}`} style={{ width: `${percent}%` }} />
      </div>
      {nearlyFull && <p className="text-sm text-amber-800">Almost full. Delete files you no longer need, or ask the admin for more space.</p>}
    </section>
  )
}

function DeleteAccountDialog({ open, email, onClose }: { open: boolean; email: string; onClose: () => void }) {
  const [typed, setTyped] = useState('')
  const deleteAccount = useDeleteMyAccount()
  const navigate = useNavigate()
  const { reset } = deleteAccount
  // Stable, because Modal re-focuses its panel whenever onClose changes (which would steal focus from the input).
  const close = useCallback(() => {
    setTyped('')
    reset()
    onClose()
  }, [reset, onClose])

  return (
    <Modal open={open} title="Delete my account?" onClose={close}>
      <p className="text-base text-muted">
        This permanently deletes your account with all your records, doctors, laboratories and files. It cannot be
        undone. Download your data first if you want to keep a copy. Copies inside the encrypted server backups
        disappear as those backups expire, within 6 months.
      </p>
      <div className="mt-4">
        <TextInput label="Type your email to confirm" autoComplete="off" value={typed} onChange={(e) => setTyped(e.target.value)} />
      </div>
      {deleteAccount.isError && (
        <p role="alert" className="mt-3 rounded-xl bg-danger-50 p-3 text-sm text-danger-700">
          {errorMessage(deleteAccount.error)}
        </p>
      )}
      <div className="mt-5 grid grid-cols-2 gap-3">
        <Button variant="secondary" onClick={close} disabled={deleteAccount.isPending}>
          Cancel
        </Button>
        <Button
          variant="danger"
          disabled={typed.trim().toLowerCase() !== email.toLowerCase()}
          loading={deleteAccount.isPending}
          onClick={() => deleteAccount.mutate(typed, { onSuccess: () => navigate('/login', { replace: true }) })}
        >
          Delete
        </Button>
      </div>
    </Modal>
  )
}

export function ProfilePage() {
  const { data: user } = useMe()
  const logout = useLogout()
  const logoutAll = useLogoutAll()
  const [confirmingLogoutAll, setConfirmingLogoutAll] = useState(false)
  const [deletingAccount, setDeletingAccount] = useState(false)
  const closeDeleteAccount = useCallback(() => setDeletingAccount(false), [])
  const { data: privacy } = usePrivacyInfo()
  const navigate = useNavigate()

  return (
    <div className="space-y-6">
      <PageHeader title="Profile" subtitle={user?.email} />

      <StorageBar />

      <section className="space-y-3" aria-label="Browse">
        <MenuLink to="/timeline" icon={CalendarClock} title="Timeline" hint="Everything in date order" />
        <MenuLink to="/doctors" icon={Stethoscope} title="Doctors" hint="Your doctor directory" />
        <MenuLink to="/labs" icon={FlaskConical} title="Laboratories" hint="Your laboratory directory" />
        {user?.is_admin && <MenuLink to="/admin" icon={UsersRound} title="Admin" hint="Invite people and manage accounts" />}
      </section>

      <section className="space-y-3" aria-labelledby="backup-heading">
        <div>
          <h2 id="backup-heading" className="section-heading">
            Your data
          </h2>
          <p className="page-subtitle">Keep a copy of your records somewhere safe. The download contains private medical data.</p>
        </div>
        <DownloadLink href="/api/account/export" icon={Database} title="Download my data (ZIP)" hint="All your records, and every file under its own name" />
        <DownloadLink href="/api/export/json" icon={FileJson} title="Export records (JSON)" hint="Structured data without the files" />
      </section>

      <section className="space-y-3" aria-label="Account">
        <Button
          variant="secondary"
          className="w-full"
          loading={logout.isPending}
          onClick={() => logout.mutate(undefined, { onSettled: () => navigate('/login', { replace: true }) })}
        >
          <LogOut className="size-5" aria-hidden />
          Sign out
        </Button>
        <Button variant="ghost" className="w-full" onClick={() => setConfirmingLogoutAll(true)}>
          <MonitorSmartphone className="size-5" aria-hidden />
          Sign out of all devices
        </Button>
      </section>

      <section className="space-y-3" aria-labelledby="privacy-heading">
        <h2 id="privacy-heading" className="section-heading">
          Privacy
        </h2>
        <MenuLink to="/privacy" icon={ShieldCheck} title="Privacy notice" hint="What is kept, where, and your rights" />
        {privacy && (
          <p className="text-sm text-muted">
            Questions or complaints about your data: {privacy.grievance_name},{' '}
            <a href={`mailto:${privacy.grievance_email}`} className="font-semibold text-brand-700">
              {privacy.grievance_email}
            </a>
          </p>
        )}
        {user && !user.is_admin && (
          <Button variant="dangerOutline" className="w-full" onClick={() => setDeletingAccount(true)}>
            <Trash2 className="size-5" aria-hidden />
            Delete my account
          </Button>
        )}
      </section>

      {user && <DeleteAccountDialog open={deletingAccount} email={user.email} onClose={closeDeleteAccount} />}

      <ConfirmDialog
        open={confirmingLogoutAll}
        title="Sign out of all devices?"
        message="Also signs you out on this device. Use this if you lost a phone or signed in on someone else's computer."
        confirmLabel="Sign out everywhere"
        loading={logoutAll.isPending}
        error={logoutAll.isError ? errorMessage(logoutAll.error) : null}
        onCancel={() => setConfirmingLogoutAll(false)}
        onConfirm={() => logoutAll.mutate(undefined, { onSuccess: () => navigate('/login', { replace: true }) })}
      />
    </div>
  )
}
