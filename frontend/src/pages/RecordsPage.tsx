import { Link } from 'react-router-dom'
import { Menu } from 'lucide-react'
import { PageHeader } from '@/components/layout/PageHeader'
import { RecordBrowser } from '@/components/records/RecordBrowser'
import { ViewSwitch } from '@/components/records/ViewSwitch'

export function RecordsPage() {
  return (
    <>
      <PageHeader
        title="Records"
        action={
          <Link to="/more" aria-label="More options" className="grid size-11 place-items-center rounded-full text-ink hover:bg-wash">
            <Menu className="size-6" />
          </Link>
        }
      />
      <ViewSwitch active="list" />
      <RecordBrowser withSearchBox={false} />
    </>
  )
}
