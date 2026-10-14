# Medical Records: Roadmap

Work top to bottom. Each item lists what "done" means.

## Level 1: Visual fixes
- [x] #1 Bottom padding: no content hidden behind the bottom nav (safe-area aware, shared variable for nav height).
  - Notes: --bottom-nav-height in index.css is the single source: the nav's height, the shared main's .pb-bottom-nav padding (nav height + safe-area inset + 16px) and the toast position all derive from it; viewport-fit=cover is set. Re-verified on all 14 screens at 360/430px with 0 and 34px insets: ≥16px clear above the nav after scrolling to the bottom.
- [x] #2 Centred page container: equal gutters on every screen; one shared container.
  - Notes: One shared .page-container (centred, max-w-2xl, 16px gutters) in index.css, used by the app layout, the sign-in page and the server-error screen (sign-in keeps a narrower centred column). Desktop scrollbars reserve space on both edges (scrollbar-gutter). Re-verified on all 14 screens at 360/430px: equal 16px gutters, no horizontal scroll.
- [x] #3 Consistent type scale: shared page title / subtitle / section heading styles.
  - Notes: Four shared classes in index.css: .page-title (serif 24px), .page-subtitle (14px muted), .section-heading (serif 18px) and .group-heading (14px muted, Timeline day headers). Every screen, including sign-in, plus dialogs, form sections and empty states, uses them; Home uses the shared PageHeader (its menu button is the header action). Re-verified by measuring headings on all screens: exactly one style per role.
- [x] #4 Bottom nav labels share one baseline; the raised + button doesn't push its label down.
  - Notes: Every nav item has the same 28px icon slot; the + circle (44px, paper-coloured ring) rises out of its slot above the bar instead of pushing its label down. Re-verified: all labels end on the same baseline at 360/390/430px.
- [x] #5 Record card: meta line "Type · Date · N files", one vertically centred chevron, title truncates.
  - Notes: One shared RecordCard, used by Home, Records, Search and Timeline: meta reads "Type · Date · N files" (count only when there are files, pluralised), one vertically centred chevron, title truncates. Meta parts stay whole, so at 360px the line wraps between parts. Re-verified with tests (meta text, single chevron) and screenshots at 360/430px.
- [x] #6 Distinct category colours from one central type→colour map; no two types similar; none look like the primary action colour.
  - Notes: Type colours are --color-type-<type> / -soft tokens in index.css (the one central map), wired through RECORD_TYPE_INFO and used by every icon tile and badge. Blue, violet, amber, red, brown, magenta and neutral grey; replaces two greys and two blues. Re-verified: hues ≥70° from the teal brand/action colour, nearest pair ΔE(OKLab) ≈ 0.10, each strong colour ≥5:1 on its tint and the page; a test checks each type has its own tokens.
- [x] #7 Accessibility basics: aria-labels on icon buttons, nav landmark + aria-current, contrast ≥ 4.5:1 for text, 44px targets, focus-visible.
  - Notes: Audited 22 screens/states (incl. document viewer, doctor/lab forms, filter panels, dialogs, sign-in) with axe-core (WCAG 2.1 AA + best practice) plus scans for <44px targets, unlabelled icon controls and placeholder contrast: 0 issues. Muted text token is #5d6679 (≥5:1 on paper, card, wash), placeholders use it at full strength (5.8:1); chips, small buttons, tag links/suggestions and phone/email links are ≥44px; tag remove buttons have a 44px hit area. Nav landmark has aria-current; focus-visible rings throughout.

## Level 2: UX and structure
- [x] #8 Add record screen has a close/back control; cancelling with unsaved changes asks for confirmation.
  - Notes: Add form has a Close (X) control and edit form a Back arrow; Cancel/Close/Back with unsaved changes (fields or picked files) opens a "Discard changes?" dialog, and reload/tab close triggers the browser prompt. The /add picker also has Close. Deferred: bottom-nav taps and the browser Back button are not intercepted (needs a data router for useBlocker).
- [x] #9 Navigation: remove the hamburger menu; bottom nav = Home · Records · (+) · Search · Profile, with + centred. Move the old menu contents into Profile. Remove the duplicate "Add record" button and search bar from Home.
  - Notes: Bottom nav is Home · Records · (+) · Search · Profile. The More page became /profile (timeline, doctors, labs, backup/export, sign out; email shown under the title), /more redirects there, and Doctors/Labs go back to Profile. Hamburger links removed from Home, Records and Timeline; Home's search bar and Add record button removed.
- [x] #10 Type picker: + opens a bottom sheet with a 2–3 column grid of record types (icon + label), all visible without scrolling; tapping one opens that type's form. Closes on swipe down, backdrop tap or Esc.
  - Notes: The nav + (accessible name "Add record") opens a bottom sheet with a 3-column grid of all 7 types; tapping one opens /add/<type>. Closes on backdrop tap, Esc, the X, or a swipe down of 80px+ (opt-in swipeToClose on Modal, so form sheets can't be swiped away). Fits at 360px without scrolling. The /add page stays as a fallback for links and direct visits.
- [ ] #11 Records filters: horizontally scrolling filter chips (All + each type + years with records), a sort control (newest/oldest), and the list grouped under month/year headers. The filter state shows in the "N records" count.
- [ ] #12 Record type editable after saving. When adding, suggest the type from title keywords (e.g. ultrasound/MRI/CT/X-ray → Scan; CBC/blood test/lipid → Lab Report) as a dismissible suggestion, never forced.
- [ ] #13 Helpful empty states for: no records, no search results, and filters with no matches (with a clear action).

## Level 3: Core features
- [ ] #14 Family profiles. Depends on: #9. Profile model (name, relation, DOB, blood group, avatar colour). Every record belongs to a profile (migrate existing records to a default "Me" profile). Profile switcher in the header/Profile tab; all lists filter by the active profile.
- [ ] #15 Emergency card. Depends on: #14. Per profile: blood group, allergies, chronic conditions, current medicines, emergency contacts (tap to call). Reachable in one tap from Profile.
- [ ] #16 Medicine tracker. Depends on: #14. Medicine model (name, dose, frequency, timing, start/end date, linked prescription record). "Active medicines" list; medicines end automatically after the end date.
- [ ] #17 Follow-ups and appointments. Depends on: #14. Model (title, date/time, doctor, place, linked record, done flag). Create from scratch or from a record ("Add follow-up"). Upcoming / past lists.
- [ ] #18 Vaccination records. Depends on: #14. Vaccine name, dose number, date, next due date, certificate attachment.
- [ ] #19 Doctors and hospitals list built automatically from existing records' doctor/hospital fields (de-duplicated, case-insensitive), each showing its linked records. Editable details (phone, address, speciality).
- [ ] #20 Home "Today" dashboard. Depends on: #16, #17. Sections: today's medicines, next follow-up, recently added (3), quick upload. Each hides when empty.

## Level 4: Intermediate
- [ ] #21 App lock: PIN (and biometrics/WebAuthn where available), lock after X minutes in the background, hide content in the app switcher, forgot-PIN flow that doesn't silently wipe data.
- [ ] #22 Backup / export / restore: export all data + attachments as one file (zip/JSON); restore with a preview and merge-or-replace choice; show the last backup date.
- [ ] #23 Reminders/notifications for medicine doses (#16) and follow-ups (#17); per-item on/off; respect permission denial gracefully. Depends on: #16, #17.
- [ ] #24 Episodes: group related records (visit, scan, prescription, follow-up) under a named episode with its own timeline view. A record can belong to 0 or 1 episode.
- [ ] #25 Doctor summary PDF: choose a profile, date range and record types → PDF with profile basics, emergency info, active medicines, and a record list with key details. Generated on the device.
- [ ] #26 Insurance and bills: policy details per profile, bills attached to records with amount, and claim status (not filed / filed / settled).

## Level 5: Advanced
- [ ] #27 Encrypted storage at rest for records and attachments (key derived from the app lock PIN, or a secure key store). Depends on: #21. Includes a migration of existing data.
- [ ] #28 Scan a report: camera/upload → OCR → pre-fill date, doctor, hospital, title and suggested type for the user to confirm. Prefer on-device OCR. Any cloud service needs my approval first.
- [ ] #29 Full-text search inside attachments using the OCR text. Depends on: #28.
- [ ] #30 Lab values and trends: structured test results (test, value, unit, reference range, date), manual entry first, OCR-assisted later; a trend chart per test; out-of-range values flagged.
- [ ] #31 Time-limited share link/QR code for selected records (needs a backend; expiry + revoke). Plan and get my approval before building.
- [ ] #32 ABHA/ABDM integration to link and pull health records. Research and plan only until I approve.
