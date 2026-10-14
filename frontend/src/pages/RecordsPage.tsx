import { PageHeader } from '@/components/layout/PageHeader'
import { RecordBrowser } from '@/components/records/RecordBrowser'
import { ViewSwitch } from '@/components/records/ViewSwitch'

export function RecordsPage() {
  return (
    <>
      <PageHeader title="Records" />
      <ViewSwitch active="list" />
      <RecordBrowser withSearchBox={false} />
    </>
  )
}
