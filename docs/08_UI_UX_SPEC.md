# 08 — UI / UX Specification

## 1. Design system
- **Brand**: MUDHOTECH HR RECRUITING SYSTEM. Primary `#1F4E94` (deep blue), accent `#0EA5A4` (teal), success `#15803D`, warning `#B45309`, danger `#B91C1C`, neutrals slate. Font: Inter (self-hosted via `next/font`). Light + dark themes via CSS variables (shadcn tokens).
- Components: shadcn/ui (Button, Input, Select, Combobox, Dialog, Sheet, Tabs, Table, Badge, Tooltip, Toast, Stepper (custom), Card, Skeleton, Alert, Command palette).
- Custom: `DataTable` (TanStack Table; server pagination, column visibility, saved views), `StatusBadge` (application/job states — consistent colours + text, never colour-only), `BandBadge` (AI band with "AI suggestion" label), `EvidenceViewer` (pdf.js page render + highlight + claim list), `CriteriaPanel`, `ScoreBreakdown` (bars per category with coverage hatch), `Timeline`, `RichTextEditor` (TipTap minimal: headings, lists, bold, italic, links), `FileUploader` (presign, progress, retry, scan status), `WizardShell` (steps, autosave indicator "Saved · 2s ago"), `EmptyState`, `ErrorState`, `ConfirmDialog` (with reason field), `OrgSwitcher`, `NotificationBell`.
- AI content is always visually labelled **"AI-assisted suggestion — requires human review"**.
- Microcopy rules: plain English, respectful candidate messages, never "rejected" — use "not selected".

## 2. Route map
### Public `(public)`
| Route | Page |
|---|---|
| `/` | Hero search, featured/latest jobs, how it works, for employers CTA |
| `/jobs` | Search + filters + results (SSR, URL-state filters) |
| `/jobs/[slug]` | Job detail, company card, deadline (job TZ + local), requirements (essential/preferred), Apply button, share, JSON-LD |
| `/companies/[slug]` | Company careers page |
| `/employers` | Product page for organisations + sign-up |
| `/how-we-use-ai`, `/privacy`, `/terms`, `/accessibility` | Policy pages |
| `/login`, `/register`, `/verify-email`, `/forgot-password`, `/reset-password`, `/mfa` | Auth |
| `/invitations/[token]` | Accept staff invitation |

### Candidate `(candidate)`
| `/candidate/dashboard` | Applications summary, actions needed (clarifications, re-uploads), recommended jobs (simple FTS on profile skills) |
| `/candidate/profile` | Profile sections; import from CV; completeness meter |
| `/candidate/documents` | CV library, parse results, corrections |
| `/candidate/applications` · `/candidate/applications/[id]` | Status timeline, submitted answers (read-only), clarifications, messages, withdraw |
| `/apply/[jobId]` | 6-step wizard (Contact & privacy → Experience → Documents → Questions → Review & correct → Submitted) |
| `/candidate/privacy` | Consents, rights requests, download my data |
| `/candidate/settings` | Account, email, password, MFA (optional), notifications |

### HR `(hr)`
| `/hr/dashboard` | KPI cards, queues (errors, pending reviews, approvals, clarifications), recent activity |
| `/hr/jobs` | Jobs table with status filters |
| `/hr/jobs/new` · `/hr/jobs/[id]/edit` | 5-step job wizard with publish-readiness checklist sidebar |
| `/hr/jobs/[id]` | Overview: status, version history, funnel, assignments, actions (approve/publish/pause/close) |
| `/hr/jobs/[id]/applications` | Applicants DataTable (band, score, coverage, flags, status, criteria-met chips), saved views, bulk actions; pipeline (kanban) toggle |
| `/hr/jobs/[id]/screening` | Screening runs, progress, failures with retry, distribution chart, low-coverage warning |
| `/hr/jobs/[id]/shortlist` | Shortlist builder: suggested list, uncertain list, desired size, decisions + reasons, submit/approve, undo countdown |
| `/hr/applications/[id]` | Candidate review: left = EvidenceViewer (CV), right = tabs (Criteria & evidence, Answers, Profile, Flags, Timeline, Notes, Messages, Evaluation versions); actions bar (transition, request clarification, verify claim) |
| `/hr/compare?ids=` | Side-by-side comparison (≤4) |
| `/hr/interviews` (v1.1), `/hr/offers` (v1.1), `/hr/talent-pool` (v1.1) | |
| `/hr/reports` | Dashboard + exports |
| `/hr/settings/{organisation,team,policies,templates,question-bank,skills,privacy,audit,billing,integrations}` | |

### Admin `(admin)`
`/admin/dashboard`, `/admin/organisations[/id]`, `/admin/users`, `/admin/plans`, `/admin/feature-flags`, `/admin/taxonomy`, `/admin/model-registry`, `/admin/queues`, `/admin/dead-letters`, `/admin/audit-logs`, `/admin/system-health`, `/admin/support-access`.

## 3. Key screen specs
### 3.1 Application wizard (mobile-first)
- Sticky progress header "Step 3 of 6 — Documents"; autosave indicator; "Save & exit".
- Documents step: drag/drop + "Choose file"; shows accepted types/limits; per-file progress, cancel, retry; scan status chip (Scanning… → Ready / Problem: re-upload).
- Questions step: renders by type; conditional questions appear inline with aria-live announce; word counter; required markers with text "(required)".
- Review step: summary of all inputs + "What we extracted from your CV" with edit/correct links; consent checkboxes (application processing — required; AI-assisted screening notice — informational + link to object option); Submit button disabled while submitting; idempotency key generated per attempt session.
- Confirmation: reference number, what happens next, timeline expectations, link to status page.

### 3.2 HR applicants table
Columns: Candidate (or "Candidate #A12" in blind mode), Band (badge), Score (with coverage ring), Essentials (✓ n / ? n / ✗ n), Flags (icons with tooltips + text), Status, Submitted, Assigned. Row click → review page. Bulk select → actions (assign, tag, propose shortlist, request clarification, transition with reason). Saved views: "Needs review", "Recommended", "Errors", "Eligibility review".

### 3.3 Candidate review page
EvidenceViewer: clicking a criterion highlights matching snippets on the CV page; hovering a snippet shows which criteria it supports. Criteria panel shows per criterion: status icon, score band, method (exact/alias/semantic/answer/human), confidence, evidence list, "Verify / Correct / Not supported" actions. Flags banner on top (e.g. "Scanned CV — OCR confidence 62%").

### 3.4 Shortlist builder
Three columns: Suggested (recommended_for_review sorted by score), Needs your review (review_needed + eligibility_review), Others (lower_match). Desired size input. Decision chips per candidate. Summary bar: "8 shortlisted · 3 on hold · 0 not selected · 12 undecided". Approve requires undecided=0 or explicit "leave undecided in review". Undo countdown after approval.

## 4. States & feedback
Every data view implements: loading skeleton, empty state with next action, error state with retry and request_id, permission-denied state. Toasts for success; inline errors for forms; optimistic updates only for non-consequential actions (notes, tags).

## 5. Accessibility checklist (per page)
Landmarks, single h1, logical heading order, labels + descriptions, error summary at top on submit with links to fields, focus management on step change/dialog open, skip link, 24px targets, contrast, `prefers-reduced-motion`, tables with `<th scope>`, charts with data table alternative, no info by colour alone, timeouts warn 2 min before session expiry with extend.

## 6. Performance budget
Public routes RSC, no client data fetching on first paint; images via `next/image`; fonts subset; route-level code splitting; HR tables virtualised for > 200 rows.

## 7. i18n
`next-intl`, `messages/en.json`; keys by feature; dates via `Intl.DateTimeFormat` with job/user timezone; currencies `Intl.NumberFormat`. Shona (`sn`) and Ndebele (`nd`) files added in Phase 15.
