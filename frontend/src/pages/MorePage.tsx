import { CalendarClock, ChevronRight, Database, FileJson, FlaskConical, LogOut, Stethoscope, type LucideIcon } from 'lucide-react'
import { Link, useNavigate } from 'react-router-dom'
import { PageHeader } from '@/components/layout/PageHeader'
import { Button } from '@/components/ui/Button'
import { useLogout, useMe } from '@/hooks/queries'

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

export function MorePage() {
  const { data: user } = useMe()
  const logout = useLogout()
  const navigate = useNavigate()

  return (
    <div className="space-y-6">
      <PageHeader title="More" back />

      <section className="space-y-3" aria-label="Browse">
        <MenuLink to="/timeline" icon={CalendarClock} title="Timeline" hint="Everything in date order" />
        <MenuLink to="/doctors" icon={Stethoscope} title="Doctors" hint="Your doctor directory" />
        <MenuLink to="/labs" icon={FlaskConical} title="Laboratories" hint="Your laboratory directory" />
      </section>

      <section className="space-y-3" aria-labelledby="backup-heading">
        <div>
          <h2 id="backup-heading" className="section-heading">
            Backup and export
          </h2>
          <p className="page-subtitle">Keep a copy of your records somewhere safe. Backups contain private medical data.</p>
        </div>
        <DownloadLink href="/api/backup" icon={Database} title="Full backup (ZIP)" hint="Database and all uploaded files" />
        <DownloadLink href="/api/export/json" icon={FileJson} title="Export records (JSON)" hint="Structured data without the files" />
      </section>

      <section className="space-y-3" aria-label="Account">
        {user && <p className="text-sm text-muted">Signed in as {user.email}</p>}
        <Button
          variant="secondary"
          className="w-full"
          loading={logout.isPending}
          onClick={() => logout.mutate(undefined, { onSettled: () => navigate('/login', { replace: true }) })}
        >
          <LogOut className="size-5" aria-hidden />
          Sign out
        </Button>
      </section>
    </div>
  )
}
