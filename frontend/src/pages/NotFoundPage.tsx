import { SearchX } from 'lucide-react'
import { LinkButton } from '@/components/ui/Button'
import { EmptyState } from '@/components/ui/feedback'

export function NotFoundPage() {
  return <EmptyState icon={SearchX} title="Page not found" description="That page does not exist." action={<LinkButton to="/">Go home</LinkButton>} />
}
