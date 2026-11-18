# Pilot support process (P11-T11)

How pilot organisations and their candidates get help during the v1.0 pilot, and how MudhoTech handles it.
Engineering incidents follow `docs/runbooks/`; this document covers user support.

## Channels
| Who | Channel | Hours (Africa/Harare) |
|---|---|---|
| HR staff of pilot organisations | support email (`SUPPORT_EMAIL`), named pilot contact by phone/WhatsApp for urgent issues | Mon–Fri 08:00–17:00 |
| Candidates | the employer first (application **Messages**); account problems → *Forgot password* or the support email shown in the footer | best effort, next working day |
| Security / privacy reports | support email with subject `SECURITY` or `PRIVACY` — triaged the same day | every day |

Candidates never get support by replying to notification emails (no-reply mailbox, ADR-024).

## Severity and response targets
| Severity | Examples | First response | Target fix / workaround |
|---|---|---|---|
| **S1 — critical** | site down; submissions failing; data shown to the wrong organisation; suspected breach | 30 min (business hours), 2 h otherwise | workaround same day; incident runbook (`incident-data-leak.md` if data is involved) |
| **S2 — high** | a core flow blocked for one organisation (cannot publish, cannot approve a shortlist, emails not arriving) | 2 h | 1 working day |
| **S3 — normal** | a bug with a workaround; confusing screen; wrong translation | 1 working day | next release |
| **S4 — request** | feature idea, report, training question | 2 working days | backlog review |

## Handling a request
1. **Log it** in the pilot tracker: date, organisation, role, severity, short description. **No personal data**
   (no candidate names, CV content or email addresses) — refer to applications by reference (`MHRS-…`).
2. **Reproduce** on staging with synthetic data when possible. If production data is needed, use **support access**
   (break-glass): read-only, approved by a second MudhoTech admin, at most 4 hours, every page opened is logged,
   and the organisation sees a banner and the grant under **Settings → Privacy**, where it can revoke it
   (Org admin guide §5). Tell the organisation before requesting it.
3. **Respond** with the workaround or the plan; link the relevant guide section.
4. **Escalate** S1/S2 to the engineer on call (alarm runbooks), and the owner for anything involving personal data,
   legal questions or an organisation's complaint.
5. **Close** with the fix version; the weekly review turns repeated questions into guide or UI improvements.

## Decisions about candidates are never made by support
Support staff do not change application statuses, scores or shortlists, and never advise an organisation on whom
to hire. Complaints about a hiring decision go to the organisation (the controller); the organisation can
**reconstruct** the decision as a PDF from the audit log to answer them.

## Candidate rights requests
Candidates use **Account → Privacy** (export, correction, deletion, objection to automated processing). Support
can explain the process but does not handle the data; the organisation's admin (and the platform admin for
account-level deletion) acts on the request in the app, within the deadlines shown there.

## Weekly pilot review (30 min, owner + engineering + pilot contacts)
- open S1/S2 items; new S3/S4 items and their priority;
- operational health: alarms fired, dead letters, processing backlog, email failures;
- AI oversight: override analytics per vacancy (> 30 % → review the rubric with the organisation), grounding and
  quality counters;
- feedback from HR sessions; guide/video updates needed.

## Pilot exit
After the agreed pilot period (default 8 weeks): retrospective with each organisation (what worked, adoption,
time-to-shortlist, fairness checks), go/no-go for general availability, and the Phase 12+ backlog.
