import { Link } from 'react-router-dom'
import { PrivacyNotice } from '@/components/privacy/PrivacyNotice'
import { useMe } from '@/hooks/queries'

/** The privacy notice, readable without signing in (linked from the login and invite pages and from Profile). */
export function PrivacyPage() {
  const { data: user } = useMe()
  return (
    <main className="page-container max-w-2xl space-y-6 py-8">
      <div>
        <Link to={user ? '/profile' : '/login'} className="font-semibold text-brand-700">
          ← {user ? 'Profile' : 'Sign in'}
        </Link>
        <h1 className="page-title mt-4">Privacy notice</h1>
      </div>
      <PrivacyNotice />
    </main>
  )
}
