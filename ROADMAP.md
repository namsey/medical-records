# Medical Records: Roadmap

Work top to bottom. Each item lists what "done" means.

## Level 1: Visual fixes
- [x] #1 Bottom padding: no content hidden behind the bottom nav (safe-area aware, shared variable for nav height).
  - Notes: --bottom-nav-height in index.css is the single source: the nav's height, the shared main's .pb-bottom-nav padding (nav height + safe-area inset + 16px) and the toast position all derive from it; viewport-fit=cover is set. Re-verified on all 14 screens at 360/430px with 0 and 34px insets: ≥16px clear above the nav after scrolling to the bottom.
- [x] #2 Centred page container: equal gutters on every screen; one shared container.
  - Notes: One shared .page-container (centred, max-w-2xl, 16px gutters) in index.css, used by the app layout, the sign-in page and the server-error screen (sign-in keeps a narrower centred column). Desktop scrollbars reserve space on both edges (scrollbar-gutter). Re-verified on all 14 screens at 360/430px: equal 16px gutters, no horizontal scroll.
- [x] #3 Consistent type scale: shared page title / subtitle / section heading styles.
  - Notes: Four shared classes in index.css: .page-title (serif 24px), .page-subtitle (14px muted), .section-heading (serif 18px) and .group-heading (14px muted: Records month headers, Timeline day headers). Every screen, including sign-in, plus dialogs, form sections and empty states, uses them; Home uses the shared PageHeader. Re-verified by measuring headings on all screens: exactly one style per role.
- [x] #4 Bottom nav labels share one baseline; the raised + button doesn't push its label down.
  - Notes: Every nav item has the same 28px icon slot; the + circle (44px, paper-coloured ring) rises out of its slot above the bar instead of pushing its label down. Re-verified: all five labels end on the same baseline at 360/390/430px.
- [x] #5 Record card: meta line "Type · Date · N files", one vertically centred chevron, title truncates.
  - Notes: One shared RecordCard, now used by Home, Records, Search and Timeline: meta reads "Type · Date · N files" (count only when there are files, pluralised), one vertically centred chevron, title truncates. Meta parts stay whole, so at 360px the line wraps between parts. Re-verified with tests (meta text, single chevron) and screenshots at 360/430px.
- [x] #6 Distinct category colours from one central type→colour map; no two types similar; none look like the primary action colour.
  - Notes: Type colours are --color-type-<type> / -soft tokens in index.css (the one central map), wired through RECORD_TYPE_INFO and used by every icon tile and badge. Blue, violet, amber, red, brown, magenta and neutral grey; replaces two greys and two blues. Re-verified: hues ≥70° from the teal brand/action colour, nearest pair ΔE(OKLab) ≈ 0.10, each strong colour ≥5:1 on its tint and the page; a test checks each type has its own tokens.
- [x] #7 Accessibility basics: aria-labels on icon buttons, nav landmark + aria-current, contrast ≥ 4.5:1 for text, 44px targets, focus-visible.
  - Notes: Audited 25 screens/states (incl. document viewer, doctor/lab forms, filter panels, type sheet, dialogs, sign-in) with axe-core (WCAG 2.1 AA + best practice) plus scans for <44px targets, unlabelled icon controls and placeholder contrast: 0 issues. Muted text token is #5d6679 (≥5:1 on paper, card, wash), placeholders use it at full strength (5.8:1); chips, small buttons, tag links/suggestions, phone/email links and the suggestion dismiss button are ≥44px; tag remove buttons have a 44px hit area. Nav landmark has aria-current; focus-visible rings throughout.

## Level 2: UX and structure
- [x] #8 Add record screen has a close/back control; cancelling with unsaved changes asks for confirmation.
  - Notes: Add form has a Close (X), edit form a Back arrow, and the /add picker a Close. Any exit with unsaved changes (Cancel, Close/Back, a bottom-nav tab, the type sheet, browser Back) shows "Discard changes?" (Keep editing / Discard) via a data router + useBlocker; reload/tab close uses the browser prompt; saving is never blocked. Re-verified by tests and in Chromium for browser Back.
- [x] #9 Navigation: remove the hamburger menu; bottom nav = Home · Records · (+) · Search · Profile, with + centred. Move the old menu contents into Profile. Remove the duplicate "Add record" button and search bar from Home.
  - Notes: Bottom nav is Home · Records · (+) · Search · Profile with the + exactly centred (re-measured at 360/430px). The old More page is the Profile tab (timeline, doctors, labs, backup/export, sign out); /more redirects there; no hamburger menu or /more links remain. Home has no search bar or Add record button (both covered by tests).
- [x] #10 Type picker: + opens a bottom sheet with a 2–3 column grid of record types (icon + label), all visible without scrolling; tapping one opens that type's form. Closes on swipe down, backdrop tap or Esc.
  - Notes: The nav + opens a bottom sheet with a 3-column grid of all 7 types (icon + label); tapping one opens its form. Closes on swipe down (80px+), backdrop tap, Esc or the X; swipe is opt-in on Modal so form sheets can't be swiped away. Re-verified: no scrolling needed at 360/430px wide, down to a 568px-tall screen; each close path is tested.
- [x] #11 Records filters: horizontally scrolling filter chips (All + each type + years with records), a sort control (newest/oldest), and the list grouped under month/year headers. The filter state shows in the "N records" count.
  - Notes: Records has one scrolling chip row (All, each type, then each year with records from GET /api/years), a Newest/Oldest sort, month/year group headers, and a count worded from the filters (e.g. "3 lab reports in 2026"). Type, year and sort live in the URL; tags and date range stay in the Filters panel (a year narrows the range). Re-verified by the Records flow test and unit tests.
- [x] #12 Record type editable after saving. When adding, suggest the type from title keywords (e.g. ultrasound/MRI/CT/X-ray → Scan; CBC/blood test/lipid → Lab Report) as a dismissible suggestion, never forced.
  - Notes: Add and edit forms have a Record type select; values are kept while switching, an inline note lists details the new type won't keep, and saving asks "Remove details?" first, so nothing is dropped silently (backend PUT accepts the type change, tested). When adding, title keywords (MRI/ultrasound/CT/X-ray → Scan, CBC/blood test/lipid → Lab Report, …) show a dismissible suggestion with a Switch button; it never switches by itself.
- [x] #13 Helpful empty states for: no records, no search results, and filters with no matches (with a clear action).
  - Notes: Records, Search and Timeline tell apart: no records at all ("No records yet"/"Nothing on the timeline" + Add your first record), a search with no results ("No results for …", spelling hint or the active filters named, Clear search, plus Clear filters when filters are on), and filters with no matches ("No records match these filters" naming them, Clear filters that keeps search and sort). Home has its own no-records state. Each case and its action is covered by a test.

## Engineering
- [x] #34 Tests and CI: Playwright end-to-end tests for the core flows at 390px width (add a record of each type with an attachment, view, edit, delete, search, filter, List/Timeline toggle), and a GitHub Actions workflow that runs install, lint, build and the tests on every PR to main.
  - Notes: Playwright suite (frontend/e2e, 7 steps, ~15s) runs the real app at 390px against a throwaway database: adds all 7 record types with PDF/PNG attachments, views one and its attachment, edits, deletes, searches, filters by type/year chips, and toggles List/Timeline. Signs in via a session created directly in the test database (no test-only login route). Lint: Ruff (backend) and oxlint (frontend; typescript-eslint doesn't support TypeScript 7 yet). .github/workflows/ci.yml runs backend, frontend and end-to-end jobs on every PR to main. Deferred: two existing React patterns are lint warnings, not errors (RecordBrowser latest-ref, PdfViewer loading reset).

## Parked (not planned)
Do not implement or suggest these unless I explicitly ask.

### Level 3: Core features
- [ ] #14 Family profiles. Depends on: #9. Profile model (name, relation, DOB, blood group, avatar colour). Every record belongs to a profile (migrate existing records to a default "Me" profile). Profile switcher in the header/Profile tab; all lists filter by the active profile.
- [ ] #15 Emergency card. Depends on: #14. Per profile: blood group, allergies, chronic conditions, current medicines, emergency contacts (tap to call). Reachable in one tap from Profile.
- [ ] #16 Medicine tracker. Depends on: #14. Medicine model (name, dose, frequency, timing, start/end date, linked prescription record). "Active medicines" list; medicines end automatically after the end date.
- [ ] #17 Follow-ups and appointments. Depends on: #14. Model (title, date/time, doctor, place, linked record, done flag). Create from scratch or from a record ("Add follow-up"). Upcoming / past lists.
- [ ] #18 Vaccination records. Depends on: #14. Vaccine name, dose number, date, next due date, certificate attachment.
- [ ] #19 Doctors and hospitals list built automatically from existing records' doctor/hospital fields (de-duplicated, case-insensitive), each showing its linked records. Editable details (phone, address, speciality).
- [ ] #20 Home "Today" dashboard. Depends on: #16, #17. Sections: today's medicines, next follow-up, recently added (3), quick upload. Each hides when empty.

### Level 4: Intermediate
- [ ] #21 App lock: PIN (and biometrics/WebAuthn where available), lock after X minutes in the background, hide content in the app switcher, forgot-PIN flow that doesn't silently wipe data.
- [ ] #22 Backup / export / restore: export all data + attachments as one file (zip/JSON); restore with a preview and merge-or-replace choice; show the last backup date.
- [ ] #23 Reminders/notifications for medicine doses (#16) and follow-ups (#17); per-item on/off; respect permission denial gracefully. Depends on: #16, #17.
- [ ] #24 Episodes: group related records (visit, scan, prescription, follow-up) under a named episode with its own timeline view. A record can belong to 0 or 1 episode.
- [ ] #25 Doctor summary PDF: choose a profile, date range and record types → PDF with profile basics, emergency info, active medicines, and a record list with key details. Generated on the device.
- [ ] #26 Insurance and bills: policy details per profile, bills attached to records with amount, and claim status (not filed / filed / settled).

### Level 5: Advanced
- [ ] #27 Encrypted storage at rest for records and attachments (key derived from the app lock PIN, or a secure key store). Depends on: #21. Includes a migration of existing data.
- [ ] #28 Scan a report: camera/upload → OCR → pre-fill date, doctor, hospital, title and suggested type for the user to confirm. Prefer on-device OCR. Any cloud service needs my approval first.
- [ ] #29 Full-text search inside attachments using the OCR text. Depends on: #28.
- [ ] #30 Lab values and trends: structured test results (test, value, unit, reference range, date), manual entry first, OCR-assisted later; a trend chart per test; out-of-range values flagged.
- [ ] #31 Time-limited share link/QR code for selected records (needs a backend; expiry + revoke). Plan and get my approval before building.
- [ ] #32 ABHA/ABDM integration to link and pull health records. Research and plan only until I approve.
