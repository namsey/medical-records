import { FolderOpen } from 'lucide-react'
import { Link } from 'react-router-dom'
import { RecordCard } from '@/components/records/RecordCard'
import { LinkButton } from '@/components/ui/Button'
import { CardSkeletons, EmptyState, ErrorMessage } from '@/components/ui/feedback'
import { useRecentRecords } from '@/hooks/queries'
import { errorMessage } from '@/lib/api'

export function HomePage() {
  const recent = useRecentRecords(8)

  return (
    <div className="space-y-6 pt-2">
      <header>
        <h1 className="text-3xl font-semibold leading-tight">Medical Records</h1>
        <p className="text-sm text-muted">Your private health journal</p>
      </header>

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
