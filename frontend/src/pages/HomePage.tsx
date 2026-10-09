import { FolderOpen, Menu, Plus, Search } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { RecordCard } from '@/components/records/RecordCard'
import { LinkButton } from '@/components/ui/Button'
import { CardSkeletons, EmptyState, ErrorMessage } from '@/components/ui/feedback'
import { useRecentRecords } from '@/hooks/queries'
import { errorMessage } from '@/lib/api'

export function HomePage() {
  const [text, setText] = useState('')
  const navigate = useNavigate()
  const recent = useRecentRecords(8)

  function search(event: FormEvent) {
    event.preventDefault()
    navigate(text.trim() ? `/search?q=${encodeURIComponent(text.trim())}` : '/search')
  }

  return (
    <div className="space-y-6 pt-2">
      <header className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-semibold leading-tight">Medical Records</h1>
          <p className="text-sm text-muted">Your private health journal</p>
        </div>
        <Link to="/more" aria-label="More options" className="grid size-12 place-items-center rounded-full border border-line bg-white text-ink hover:bg-wash">
          <Menu className="size-6" />
        </Link>
      </header>

      <form role="search" onSubmit={search} className="relative">
        <Search className="pointer-events-none absolute left-3.5 top-1/2 size-5 -translate-y-1/2 text-muted" aria-hidden />
        <input
          type="search"
          enterKeyHint="search"
          value={text}
          onChange={(event) => setText(event.target.value)}
          placeholder="Search doctor, medicine, test…"
          aria-label="Search records"
          maxLength={200}
          className="field-input min-h-14 rounded-2xl pl-11"
        />
      </form>

      <LinkButton to="/add" className="w-full min-h-14 text-lg">
        <Plus className="size-6" aria-hidden />
        Add record
      </LinkButton>

      <section className="space-y-3" aria-labelledby="recent-heading">
        <div className="flex items-baseline justify-between">
          <h2 id="recent-heading" className="text-xl font-semibold">
            Recent records
          </h2>
          {recent.data && recent.data.total > 0 && (
            <Link to="/records" className="inline-flex min-h-11 items-center text-sm font-semibold text-brand-700">
              View all ({recent.data.total})
            </Link>
          )}
        </div>

        {recent.isPending && <CardSkeletons count={3} />}
        {recent.isError && <ErrorMessage message={errorMessage(recent.error)} onRetry={() => void recent.refetch()} />}
        {recent.data && recent.data.items.length === 0 && (
          <div className="card">
            <EmptyState icon={FolderOpen} title="No records yet" description="Add a prescription, lab report or doctor visit to get started." action={<LinkButton to="/add">Add your first record</LinkButton>} />
          </div>
        )}
        {recent.data && recent.data.items.length > 0 && (
          <ul className="space-y-3">
            {recent.data.items.map((record) => (
              <li key={record.id}>
                <RecordCard record={record} />
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  )
}
