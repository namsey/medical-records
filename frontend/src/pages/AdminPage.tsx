import { Check, Copy, MailPlus, UserRound } from 'lucide-react'
import { useCallback, useState, type FormEvent } from 'react'
import { PageHeader } from '@/components/layout/PageHeader'
import { Button } from '@/components/ui/Button'
import { TextInput } from '@/components/ui/Field'
import { CardSkeletons, ErrorMessage } from '@/components/ui/feedback'
import { ConfirmDialog, Modal } from '@/components/ui/Modal'
import { useToast } from '@/components/ui/Toast'
import { useAdminInvites, useAdminUsers, useCreateInvite, useDeleteUser, useMe, useRevokeInvite, useSetUserDisabled } from '@/hooks/queries'
import { errorMessage } from '@/lib/api'
import { formatDate, formatFileSize, pluralize } from '@/lib/format'
import type { AdminUser, CreatedInvite, Invite, InviteStatus } from '@/lib/types'
import { NotFoundPage } from './NotFoundPage'

const STATUS_STYLES: Record<InviteStatus, string> = {
  pending: 'bg-brand-50 text-brand-800',
  used: 'bg-wash text-muted',
  expired: 'bg-amber-100 text-amber-800',
  revoked: 'bg-danger-50 text-danger-700',
}

const STATUS_LABELS: Record<InviteStatus, string> = { pending: 'Pending', used: 'Used', expired: 'Expired', revoked: 'Revoked' }

function Badge({ className, children }: { className: string; children: string }) {
  return <span className={`inline-flex rounded-full px-2.5 py-0.5 text-xs font-semibold ${className}`}>{children}</span>
}

function NewInviteLink({ invite }: { invite: CreatedInvite }) {
  const [copied, setCopied] = useState(false)
  const toast = useToast()

  async function copy() {
    try {
      await navigator.clipboard.writeText(invite.link)
      setCopied(true)
    } catch {
      toast.error('Could not copy. Select the link and copy it yourself.')
    }
  }

  return (
    <div className="card space-y-3 border-brand-700/30 p-4" role="status">
      <p className="text-sm">
        Invite for <span className="font-semibold">{invite.email}</span>. Send this link yourself, for example by
        message. It works once, until {formatDate(invite.expires_at)}, and is <span className="font-semibold">only shown now</span>.
      </p>
      <input readOnly value={invite.link} aria-label="Invite link" className="field-input font-mono text-sm" onFocus={(e) => e.currentTarget.select()} />
      <Button variant="secondary" className="w-full" onClick={() => void copy()}>
        {copied ? <Check className="size-5" aria-hidden /> : <Copy className="size-5" aria-hidden />}
        {copied ? 'Copied' : 'Copy link'}
      </Button>
    </div>
  )
}

function InviteForm() {
  const [email, setEmail] = useState('')
  const [created, setCreated] = useState<CreatedInvite | null>(null)
  const createInvite = useCreateInvite()

  function submit(event: FormEvent) {
    event.preventDefault()
    createInvite.mutate(email.trim(), {
      onSuccess: (invite) => {
        setCreated(invite)
        setEmail('')
      },
    })
  }

  return (
    <div className="space-y-3">
      <form onSubmit={submit} className="card space-y-3 p-4" noValidate>
        <TextInput
          label="Email address"
          type="email"
          autoComplete="off"
          inputMode="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          hint="They must sign in with the Google account for this email."
          error={createInvite.isError ? errorMessage(createInvite.error) : null}
        />
        <Button type="submit" className="w-full" loading={createInvite.isPending} disabled={!email.trim()}>
          <MailPlus className="size-5" aria-hidden />
          Create invite link
        </Button>
      </form>
      {created && <NewInviteLink invite={created} />}
    </div>
  )
}

function InviteList() {
  const { data: invites, isPending, isError, error, refetch } = useAdminInvites()
  const revoke = useRevokeInvite()
  const [revoking, setRevoking] = useState<Invite | null>(null)
  const toast = useToast()

  if (isPending) return <CardSkeletons count={2} />
  if (isError) return <ErrorMessage message={errorMessage(error)} onRetry={() => void refetch()} />
  if (invites.length === 0) return <p className="text-sm text-muted">No invites yet.</p>

  return (
    <>
      <ul className="space-y-3">
        {invites.map((invite) => (
          <li key={invite.id} className="card flex items-center gap-3 p-4">
            <div className="min-w-0 flex-1">
              <p className="truncate font-semibold">{invite.email}</p>
              <p className="text-sm text-muted">
                {invite.status === 'used' && invite.used_at ? `Used ${formatDate(invite.used_at)}` : `Expires ${formatDate(invite.expires_at)}`}
              </p>
            </div>
            <Badge className={STATUS_STYLES[invite.status]}>{STATUS_LABELS[invite.status]}</Badge>
            {invite.status === 'pending' && (
              <Button size="sm" variant="dangerOutline" onClick={() => setRevoking(invite)} aria-label={`Revoke invite for ${invite.email}`}>
                Revoke
              </Button>
            )}
          </li>
        ))}
      </ul>
      <ConfirmDialog
        open={revoking !== null}
        title="Revoke this invite?"
        message={`The link for ${revoking?.email ?? ''} will stop working.`}
        confirmLabel="Revoke"
        loading={revoke.isPending}
        error={revoke.isError ? errorMessage(revoke.error) : null}
        onCancel={() => setRevoking(null)}
        onConfirm={() =>
          revoking &&
          revoke.mutate(revoking.id, {
            onSuccess: () => {
              toast.success('Invite revoked')
              setRevoking(null)
            },
          })
        }
      />
    </>
  )
}

function DeleteUserDialog({ user, onClose }: { user: AdminUser | null; onClose: () => void }) {
  const [typed, setTyped] = useState('')
  const deleteUser = useDeleteUser()
  const toast = useToast()
  const matches = user !== null && typed.trim().toLowerCase() === user.email

  const { reset } = deleteUser
  // Stable, because Modal re-focuses its panel whenever onClose changes (which would steal focus from the input).
  const close = useCallback(() => {
    setTyped('')
    reset()
    onClose()
  }, [reset, onClose])

  return (
    <Modal open={user !== null} title="Delete this account?" onClose={close}>
      <p className="text-base text-muted">
        This permanently deletes <span className="font-semibold text-ink">{user?.email}</span>, with all of their records, doctors,
        laboratories and files. It cannot be undone.
      </p>
      <div className="mt-4">
        <TextInput label="Type the email to confirm" autoComplete="off" value={typed} onChange={(e) => setTyped(e.target.value)} />
      </div>
      {deleteUser.isError && (
        <p role="alert" className="mt-3 rounded-xl bg-danger-50 p-3 text-sm text-danger-700">
          {errorMessage(deleteUser.error)}
        </p>
      )}
      <div className="mt-5 grid grid-cols-2 gap-3">
        <Button variant="secondary" onClick={close} disabled={deleteUser.isPending}>
          Cancel
        </Button>
        <Button
          variant="danger"
          disabled={!matches}
          loading={deleteUser.isPending}
          onClick={() =>
            user &&
            deleteUser.mutate(
              { id: user.id, confirmEmail: typed },
              {
                onSuccess: () => {
                  toast.success('Account deleted')
                  close()
                },
              },
            )
          }
        >
          Delete
        </Button>
      </div>
    </Modal>
  )
}

function UserList() {
  const { data: users, isPending, isError, error, refetch } = useAdminUsers()
  const setDisabled = useSetUserDisabled()
  const [deleting, setDeleting] = useState<AdminUser | null>(null)
  const closeDelete = useCallback(() => setDeleting(null), [])
  const toast = useToast()

  if (isPending) return <CardSkeletons count={2} />
  if (isError) return <ErrorMessage message={errorMessage(error)} onRetry={() => void refetch()} />

  return (
    <>
      <ul className="space-y-3">
        {users.map((user) => (
          <li key={user.id} className="card p-4">
            <div className="flex items-start gap-3">
              <span className="grid size-10 shrink-0 place-items-center rounded-full bg-brand-50 text-brand-700">
                <UserRound className="size-5" aria-hidden />
              </span>
              <div className="min-w-0 flex-1">
                <p className="truncate font-semibold">{user.email}</p>
                {user.name && <p className="truncate text-sm text-muted">{user.name}</p>}
                <p className="text-sm text-muted">
                  {user.last_login_at ? `Last sign-in ${formatDate(user.last_login_at)}` : 'Never signed in'} ·{' '}
                  <span className="whitespace-nowrap">
                    {pluralize(user.file_count, 'file')} · {formatFileSize(user.storage_bytes)}
                  </span>
                </p>
              </div>
              {user.is_admin && <Badge className="bg-brand-50 text-brand-800">Admin</Badge>}
              {user.disabled && <Badge className="bg-danger-50 text-danger-700">Disabled</Badge>}
            </div>
            {!user.is_admin && (
              <div className="mt-3 grid grid-cols-2 gap-3">
                <Button
                  size="sm"
                  variant="secondary"
                  loading={setDisabled.isPending && setDisabled.variables?.id === user.id}
                  onClick={() =>
                    setDisabled.mutate(
                      { id: user.id, disabled: !user.disabled },
                      {
                        onSuccess: () => toast.success(user.disabled ? 'Account enabled' : 'Account disabled'),
                        onError: (err) => toast.error(errorMessage(err)),
                      },
                    )
                  }
                  aria-label={`${user.disabled ? 'Enable' : 'Disable'} ${user.email}`}
                >
                  {user.disabled ? 'Enable' : 'Disable'}
                </Button>
                <Button size="sm" variant="dangerOutline" onClick={() => setDeleting(user)} aria-label={`Delete ${user.email}`}>
                  Delete
                </Button>
              </div>
            )}
          </li>
        ))}
      </ul>
      <DeleteUserDialog user={deleting} onClose={closeDelete} />
    </>
  )
}

/** Invites and accounts. Only for the admin: anyone else gets the not-found page (the API says 404 too). */
export function AdminPage() {
  const { data: me } = useMe()
  if (!me?.is_admin) return <NotFoundPage />

  return (
    <div className="space-y-6">
      <PageHeader title="Admin" back="/profile" />

      <section className="space-y-3" aria-labelledby="invite-heading">
        <h2 id="invite-heading" className="section-heading">
          Invite someone
        </h2>
        <InviteForm />
      </section>

      <section className="space-y-3" aria-labelledby="invites-heading">
        <h2 id="invites-heading" className="section-heading">
          Invites
        </h2>
        <InviteList />
      </section>

      <section className="space-y-3" aria-labelledby="accounts-heading">
        <div>
          <h2 id="accounts-heading" className="section-heading">
            Accounts
          </h2>
          <p className="page-subtitle">Storage used per account. Nobody, including you, can see another account's records here.</p>
        </div>
        <UserList />
      </section>
    </div>
  )
}
