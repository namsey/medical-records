import { PageHeader } from '@/components/layout/PageHeader'
import { RecordBrowser } from '@/components/records/RecordBrowser'

export function SearchPage() {
  return (
    <>
      <PageHeader title="Search" />
      <RecordBrowser withSearchBox />
    </>
  )
}
