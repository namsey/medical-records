import type { ReactNode } from 'react'
import { usePrivacyInfo } from '@/hooks/queries'

// The privacy notice. When its meaning changes, also change PRIVACY_VERSION in backend/app/privacy.py so everyone
// is asked to agree again. It is a plain-language draft for the admin to review; it is not legal advice.

function Part({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="space-y-2">
      <h2 className="section-heading">{title}</h2>
      <div className="space-y-2 text-base leading-relaxed text-ink">{children}</div>
    </section>
  )
}

export function PrivacyNotice() {
  const { data: info } = usePrivacyInfo()
  const contact = info ? `${info.grievance_name} (${info.grievance_email})` : 'the administrator of this app'

  return (
    <div className="space-y-6">
      <p className="text-base leading-relaxed text-muted">
        This app is a private health journal. This notice explains, in plain words, what it keeps about you, why, where,
        who can see it, and what you can do about it{info ? ` (version ${info.version})` : ''}.
      </p>

      <Part title="What is kept">
        <ul className="list-disc space-y-1 pl-5">
          <li>Your Google account email and name, to sign you in.</li>
          <li>
            What you add: records (visits, prescriptions, lab reports, diagnoses, scans and other documents), doctors,
            laboratories, tags, notes and the files you attach. This is health data, which is sensitive.
          </li>
          <li>When you signed in, and a log of account events (sign-ins, invites, account changes). The log never holds
            your records or file names.</li>
          <li>One sign-in cookie. There is no tracking, no advertising and no analytics.</li>
        </ul>
      </Part>

      <Part title="Why">
        <p>Only to keep your health journal for you: to store, organise, search and show your records. Nothing is
          sold or shared, and nothing reads or interprets your medical data automatically.</p>
      </Part>

      <Part title="Where">
        <p>
          On one server in India (Oracle Cloud, Mumbai). Encrypted backups are kept in Oracle Cloud in Mumbai, and an
          encrypted copy of those backups on the administrator's own disk in India. Your data is not sent to any other
          service or country. Signing in uses Google, which only learns that you signed in to this app.
        </p>
      </Part>

      <Part title="Who can see it">
        <p>
          Only you. The administrator can see your email, name, when you last signed in and how much storage you use,
          but not your records or files. The administrator can disable or delete accounts. Someone with access to the
          server itself could technically reach the data; that access is limited to the administrator.
        </p>
      </Part>

      <Part title="How long it is kept">
        <p>
          Until you delete it, or delete your account. After deletion, copies inside the encrypted backups disappear as
          those backups expire, within 6 months; they are only used to recover the whole server after a failure. The
          account event log is kept for 1 year.
        </p>
      </Part>

      <Part title="Your rights">
        <ul className="list-disc space-y-1 pl-5">
          <li>See and correct your data: everything is in the app, and you can edit or delete any record.</li>
          <li>Get a copy: <span className="font-semibold">Profile → Download my data</span> gives you a ZIP of all
            your records and files.</li>
          <li>Withdraw your consent and erase your data: <span className="font-semibold">Profile → Delete my
            account</span> permanently deletes your account, records and files.</li>
          <li>Complain or ask a question: contact {contact}. If you are not satisfied with the answer, you can complain
            to the Data Protection Board of India.</li>
        </ul>
      </Part>

      <Part title="Who this app is for">
        <p>Adults (18 or older) who were invited. Keep a child's records in the parent's own account.</p>
      </Part>
    </div>
  )
}
