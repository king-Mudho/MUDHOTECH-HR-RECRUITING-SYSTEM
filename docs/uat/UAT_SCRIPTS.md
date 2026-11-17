# User acceptance test (UAT) scripts — MUDHOTECH HR RECRUITING SYSTEM

P10-T09. For HR reviewers and the owner on **staging** with demo data (`seed_demo`, then
`run_pilot_benchmark --count 100` for a realistic applicant pool). Use only synthetic CVs from
`backend/fixtures/synthetic_cvs` — never real CVs or personal data.

**How to record:** for each step mark **Pass**, **Fail** or **Blocked**, and for a failure write
what you saw and the time (the support team can find it in the audit log). Report failures in
`docs/reports/DEFECT_LOG.md` with a severity (P0–P3).

Demo accounts (password: the `DEMO_PASSWORD` given to you separately):

| Role | Account |
|---|---|
| Org admin | `admin@mudhotech-demo.test` |
| HR manager | `hr@mudhotech-demo.test` |
| Recruiter | `recruiter@mudhotech-demo.test` |
| Hiring manager | `manager@mudhotech-demo.test` |
| Interview panelist | `panel@mudhotech-demo.test` |
| Auditor | `auditor@mudhotech-demo.test` |
| Platform admin | `admin@mhrs-demo.test` |
| Candidate | register a new account with any address you control (Mailpit on staging) |

Privileged roles must set up two-factor authentication after a short grace period.

---

## UAT-01 Candidate finds a vacancy and applies

| # | Step | Expected result | Result |
|---|---|---|---|
| 1 | Open the job board, search "developer", filter by location | Matching vacancies only; closed vacancies are not listed | |
| 2 | Open the Software Developer vacancy | Description, requirements, closing date and employer are shown; "How we use AI" is linked | |
| 3 | Select **Apply**, create an account, confirm the email | You return to the application, signed in | |
| 4 | Upload a synthetic CV (PDF) | Upload progress is announced; the file is checked and accepted | |
| 5 | Review the details read from the CV, correct one | Your correction is kept | |
| 6 | Answer the questions; leave one required answer empty and continue | A clear error names the field; nothing is lost | |
| 7 | Read the privacy notice; optionally tick "fully manual review"; submit | A reference number and receipt email; the status shows **Submitted** | |
| 8 | Try to apply to the same vacancy again | You are told you already applied | |

## UAT-02 Candidate follows and withdraws an application

| # | Step | Expected result | Result |
|---|---|---|---|
| 1 | Open **Applications** | The application and its status timeline | |
| 2 | Answer a clarification request (after UAT-04 step 6) | Reply is saved; HR sees it | |
| 3 | Withdraw the application with a reason | Status **Withdrawn**; confirmation email; you may apply again if the vacancy is open | |

## UAT-03 Recruiter creates a vacancy; HR manager approves and publishes

| # | Step | Expected result | Result |
|---|---|---|---|
| 1 | Recruiter: **Jobs → New vacancy**, complete every step of the wizard | Each step saves; the readiness checklist shows what is missing | |
| 2 | Add criteria with weights; mark two as essential with a reason | Weights must add up; a question about age, religion or similar is refused with an explanation | |
| 3 | Submit for approval | Status **Pending approval**; recruiter cannot publish | |
| 4 | HR manager: approve, then publish | Vacancy appears on the public board; the rubric is now fixed (a change creates a new version) | |

## UAT-04 Screening review (100 applications)

| # | Step | Expected result | Result |
|---|---|---|---|
| 1 | HR manager: open the pilot vacancy's applicants | Every application is listed; counts match the dashboard | |
| 2 | Filter "Recommended for review", sort by score | AI content is labelled "AI-assisted suggestion — requires human review"; there is no reject band | |
| 3 | Open an application | Each criterion shows evidence linked to the CV page/line, or **unknown** when nothing was found (never a fail) | |
| 4 | Blind review is on: names and contact details are hidden; reveal identity with a reason | The reveal is recorded in the audit log | |
| 5 | Verify one claim and reject another | Your decision is recorded; the evaluation is re-run as a new version | |
| 6 | Ask one candidate for clarification | Candidate is emailed; the application shows the open request | |
| 7 | Open an application whose candidate asked for manual review | No AI score, band or text anywhere | |
| 8 | Compare three applications side by side | Criteria line up; evidence links work | |

## UAT-05 Shortlist approval and undo

| # | Step | Expected result | Result |
|---|---|---|---|
| 1 | Recruiter: build a shortlist of ten; move one AI-recommended candidate to "not now" | A reason is required for every decision that differs from the AI suggestion | |
| 2 | Submit for approval | HR manager is notified | |
| 3 | HR manager: approve, leaving the rest undecided | Ten applications are **Shortlisted**; nobody is told yet; the undo window is shown | |
| 4 | Undo within the window | Statuses return; nobody was emailed | |
| 5 | Approve again and wait for the delay | Exactly the ten shortlisted candidates are emailed; nobody else hears anything | |
| 6 | Hiring manager: open the vacancy | Only shortlisted applications are visible | |

## UAT-06 Accountability and audit

| # | Step | Expected result | Result |
|---|---|---|---|
| 1 | Auditor: open the audit trail, filter by the pilot vacancy | Every decision shows who, when, reason, and the AI suggestion at the time | |
| 2 | Export the audit trail as CSV and open it in a spreadsheet | No formulas run (cells starting with `=` show as text) | |
| 3 | Reconstruct one decision (PDF) | Job version, rubric, evaluation versions with model versions, evidence and the human decision | |

## UAT-07 Privacy and rights

| # | Step | Expected result | Result |
|---|---|---|---|
| 1 | Candidate: **Privacy → Make a request → Export my data**, enter your password | A confirmation email; the request waits for confirmation | |
| 2 | Open the confirmation link | Status **Received**; after a short wait **Download my data** appears (ZIP with JSON, summary PDF, documents; 24 hours) | |
| 3 | Org admin: **Settings → Privacy**, complete the request with an outcome | The candidate sees the outcome | |
| 4 | Candidate: ask for deletion; org admin places a legal hold, then completes | The request goes **On hold** with an explanation; after the hold is released and the request completed, the candidate's data is removed | |

## UAT-08 Platform administration and AI governance

| # | Step | Expected result | Result |
|---|---|---|---|
| 1 | Platform admin: **Organisations**, verify a newly created organisation | Status **Active**; the organisation can publish | |
| 2 | Suspend it with a reason, then reactivate | Public vacancies hidden while suspended; staff read-only | |
| 3 | **AI governance**: read the model registry | Every model/engine with version, purpose, limitations and data policy | |
| 4 | Switch AI off with a reason; submit an application (UAT-01) | The application goes to manual review with no AI output; switch back on | |
| 5 | Request break-glass support access; a second platform admin approves | The organisation's staff see a banner; access is read-only and ends on time | |

## UAT-09 Accessibility and mobile (spot checks)

| # | Step | Expected result | Result |
|---|---|---|---|
| 1 | Complete UAT-01 on a phone | Every step usable at phone width | |
| 2 | Complete UAT-01 steps 1–4 with the keyboard only | Visible focus everywhere; the skip link works | |
| 3 | With a screen reader (NVDA), complete UAT-01 steps 1–2 | Headings, form labels and errors are announced (`docs/accessibility/AUDIT.md` §4) | |

---

## Sign-off

| Role | Name | Scenarios run | Open defects (P0/P1) | Decision | Signature | Date |
|---|---|---|---|---|---|---|
| HR manager (pilot employer) | | | | Accept / Accept with conditions / Reject | | |
| Recruiter (pilot employer) | | | | | | |
| Owner, MudhoTech Solutions | | | | | | |
