import type { ReactNode } from 'react'

/** The centred logo and title around the sign-in and invite pages. */
export function AuthShell({ subtitle, children }: { subtitle: string; children: ReactNode }) {
  return (
    <main className="page-container flex min-h-dvh max-w-md flex-col justify-center py-10">
      <div className="mb-8 text-center">
        <div className="mx-auto mb-5 grid size-20 place-items-center rounded-3xl bg-brand-700 text-paper shadow-md">
          <svg viewBox="0 0 64 64" className="size-11" aria-hidden>
            <path d="M26 10h12v16h16v12H38v16H26V38H10V26h16z" fill="currentColor" />
          </svg>
        </div>
        <h1 className="page-title">Medical Records</h1>
        <p className="page-subtitle mt-2">{subtitle}</p>
      </div>
      {children}
    </main>
  )
}
