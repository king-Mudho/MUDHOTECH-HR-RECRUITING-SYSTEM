# Accessibility audit — candidate and HR core journeys

P09-T13, 2026-11-17. Target: WCAG 2.2 AA (docs/06 §6, docs/08). Scope: the candidate journey
(job board → apply → applications → profile → privacy) and the HR core journey (dashboard →
vacancies → applicants → review workspace → compare → shortlist → privacy/audit settings), plus the
platform pages added in Phase 09.

## 1. Automated checks (axe-core, WCAG 2.0/2.1/2.2 A + AA)

Rule: **zero serious or critical violations**; moderate/minor findings are triaged below.

| Journey / pages | Where it runs | Gate |
|---|---|---|
| Home, job board, job detail, closed vacancy | `e2e/smoke.spec.ts`, `e2e/jobs.spec.ts` | nightly, fails on serious/critical |
| Sign-in, register, reset password | `e2e/auth.spec.ts` | nightly |
| Apply wizard (every step, errors, review, confirmation; desktop + mobile project) | `e2e/apply.spec.ts` | nightly |
| Vacancy wizard and publish (HR) | `e2e/jobs.spec.ts` | nightly |
| Candidate: dashboard, applications, profile, privacy, AI notice, jobs + keyboard walk | `e2e/a11y-journeys.spec.ts` (new) | nightly |
| HR: dashboard, vacancies, applicants, shortlist, privacy settings, audit + keyboard walk | `e2e/a11y-journeys.spec.ts` (new) | nightly |
| Core scenario (100 applicants → approved shortlist) | `e2e/core-scenario.spec.ts` | nightly (functional) |
| AI governance page (jsdom, contrast excluded) | `tests/ai-governance.test.tsx` | every push |
| Main landmark / skip-link target on every signed-in page | `tests/a11y-landmarks.test.ts` (new) | every push |

Contrast is checked only in the browser (Playwright); jsdom cannot compute it.
Animations are frozen before each axe run (`e2e/a11y.ts`) so mid-transition colours are not sampled.

## 2. Findings and fixes

| # | Finding | WCAG | Severity | Status |
|---|---|---|---|---|
| A1 | `/hr/dashboard`, `/hr/compare`, `/admin/support-access`, `/admin/model-registry` rendered no `<main id="main-content">`: no main landmark and the skip link had no target | 1.3.1, 2.4.1 | moderate (axe `landmark-one-main`, `skip-link`) | **Fixed**; guard test added |
| A2 | Earlier phases: disabled-button contrast sampled mid-transition (false positive) | 1.4.3 | — | Mitigated by `settleForAxe` |
| A3 | Review workspace keyboard shortcuts (`j`/`k`) must not fire while typing | 2.1.4 | moderate | Already handled: shortcuts ignore inputs/textareas and can be learned from the on-screen hint |
| A5 | Sticky top bar could cover the focused element when scrolling by keyboard | 2.4.11 | minor | **Fixed** (`scroll-padding-top` in `globals.css`) |
| A6 | No help link in the same place on every page | 3.2.6 | minor | Open — Phase 10 UI polish |
| A4 | Icon-only buttons (`size-6`, 24 × 24 px) are at the WCAG 2.5.8 minimum | 2.5.8 | minor | Accepted; no smaller targets exist. Prefer `size-8`+ for new controls |

No serious or critical issue was found in code review of the Phase 09 additions (privacy,
support access, AI governance): every input has a `<Label>`, errors use `role="alert"`, status
banners use `role="status"`, sections are labelled by their headings.

## 3. Keyboard walkthrough

Automated in `e2e/a11y-journeys.spec.ts` (`keyboardWalk`): Tab from the top of the page, activate the
skip link (focus target `#main-content` exists), then Tab through 25–40 stops checking that every
focused element shows a visible indicator (outline or ring) and that focus moves (no trap).

Manual walkthrough checklist (performed against the code and component behaviour; repeat on staging
before go-live):

| Step | Expected | Result |
|---|---|---|
| Skip link is the first Tab stop on every page | Visible on focus, moves to main content | Pass (all layouts; guard test) |
| Job board filters and pagination | Reachable in order, Enter/Space activate | Pass (e2e) |
| Apply wizard: Next/Back, file upload, questionnaire, review, submit | No mouse needed; error summary receives focus; fields linked to errors | Pass (e2e `apply.spec.ts`) |
| Dialogs (re-authenticate, reasons, confirm) | Focus moves into the dialog, Escape closes, focus returns to the trigger | Pass (Radix dialogs) |
| Applicants table: row actions, bulk select, filters | Tab order follows reading order; checkboxes labelled | Pass |
| Review workspace: `j`/`k` next/previous, evidence links | Shortcuts disabled in text fields; evidence viewer pages reachable | Pass |
| Shortlist builder: include/exclude/undecided, submit, approve, undo | All via buttons with text labels; reason fields required and labelled | Pass |
| Session timeout warning | Can extend with keyboard | Pass (Phase 02) |

## 4. Screen reader (NVDA) spot check

**Not performed by the agent** — there is no screen reader in the build environment. The owner (or
a tester) should run this before go-live with NVDA 2025.x + Firefox/Chrome on Windows and record the
results here:

| Check | Pages | Result | Notes |
|---|---|---|---|
| Landmarks list (Insert+F7) shows banner, navigation, main, contentinfo | job board, HR dashboard | [ ] | |
| Headings (H) give a logical outline (one h1) | job detail, applicant review | [ ] | |
| Form fields announce label, required state and errors | apply wizard, sign-in | [ ] | |
| Live regions announce upload progress, save status, bulk-action results | apply, applicants | [ ] | |
| Tables announce headers (caption + `th`) | applicants, dashboard funnel | [ ] | |
| AI content is announced as "AI-assisted suggestion — requires human review" | review workspace | [ ] | |
| Status badges are not colour-only | applications, applicants | [ ] | |

## 5. Other WCAG 2.2 checks

- 2.4.11 Focus not obscured: `scroll-padding-top` keeps focused elements below the sticky top bar
  (A5); confirm on staging.
- 2.5.8 Target size: minimum 24 × 24 px (A4).
- 3.2.6 Consistent help: **to verify** — error pages point to support with a reference; a help link
  in the same place on every page is not yet present (Phase 10 UI polish).
- 3.3.7 Redundant entry: the apply wizard pre-fills from the profile and parsed CV.
- 3.3.8 Accessible authentication: password managers and paste allowed; no cognitive tests; MFA
  with TOTP or recovery codes.
- 2.3.3 / reduced motion: `prefers-reduced-motion` respected (`globals.css`).

## 6. Result

Automated gates: zero serious/critical violations on the covered pages (nightly + per push). One
moderate structural issue (A1) fixed with a regression test. The NVDA spot check (§4) is outstanding
and is a go-live task for a human tester.
