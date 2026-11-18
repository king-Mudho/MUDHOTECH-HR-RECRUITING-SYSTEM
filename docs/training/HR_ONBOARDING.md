# HR onboarding — pilot walkthrough (P11-T11)

A 60-minute live session for each pilot organisation's HR team, plus the outline for short recorded videos.
Reference material: the role guides in `docs/user-guides/` (recruiter, HR manager, organisation admin, candidate).
Run the session on **staging** with the synthetic demo data (`seed-staging.sh --core`), never on production data.

## Who attends
| Role | Why |
|---|---|
| Organisation admin | team, policy and privacy settings |
| HR manager(s) | approve vacancies and shortlists, oversight |
| Recruiters / reviewers | create vacancies, review evidence, propose shortlists |
| (optional) Hiring manager | sees shortlisted candidates only, by default |

## Before the session (facilitator)
- [ ] Staging seeded; one demo account per attendee role (shared `DEMO_PASSWORD`, given in the session only).
- [ ] Each attendee has a laptop with a current browser; MFA app on their phone (staff accounts need MFA).
- [ ] The organisation's real vacancy text and rubric ideas ready for exercise 4 (no candidate data).
- [ ] Printed one-page "five rules" (below) for each attendee.

## The five rules (say them first, repeat them last)
1. **The AI only suggests.** People decide; every status change needs a person and a reason.
2. **Missing is unknown, never a fail.** If evidence is not found, ask the candidate (clarification).
3. **Read the evidence, not the score.** Click a criterion and look at the highlighted CV line or answer.
4. **Fair by design.** No questions or criteria about protected characteristics; blind review is on; verify
   foreign qualifications rather than discounting them.
5. **Everything is recorded.** Views of candidate data, decisions and identity reveals are in the audit log.

## Agenda (60 min)
| Time | Block | Hands-on (staging) | Guide |
|---|---|---|---|
| 0–5 | Welcome, the five rules | — | — |
| 5–10 | Sign-in and MFA | each attendee signs in, sets up the authenticator | Org admin guide §2 |
| 10–20 | **Vacancy**: wizard, criteria/rubric with weights and essentials (with reasons), screening questions; the protected-topic check refuses a question about age | create a draft from the organisation's own job text; submit for approval; HR manager approves and publishes | Recruiter §1, HR manager §1 |
| 20–35 | **Review**: applicants list, bands as routing hints, filters and saved views, blind review, the evidence view (click a criterion → highlight), flags, verify a claim, ask for clarification, compare | on the core-scenario vacancy (100 synthetic applicants): filter *Recommended*, open two applicants, verify one claim, send one clarification | Recruiter §2 |
| 35–45 | **Shortlist**: AI pre-fill as a starting point, decide with reasons when you differ, submit; HR manager approves with dual control, notification delay and **Undo** | propose 5, approve, undo, approve again | Recruiter §3, HR manager §2 |
| 45–52 | **Oversight**: dashboard, override analytics, audit log, reconstruct a decision as PDF, switching AI screening off | export the audit CSV for the vacancy | HR manager §3–5 |
| 52–57 | **Privacy**: candidates' rights requests (export, deletion), retention, legal holds | open the privacy requests page | Org admin guide §4 |
| 57–60 | Questions, how to get help (`PILOT_SUPPORT.md`), feedback form | — | — |

## Exercises checklist (each attendee)
- [ ] Signed in with MFA
- [ ] Created and submitted a vacancy with at least one justified essential
- [ ] Saw a protected-topic question refused
- [ ] Opened an application and found the evidence for a criterion
- [ ] Verified a claim and sent a clarification request
- [ ] Proposed a shortlist with one decision different from the AI suggestion, with a reason
- [ ] (HR manager) Approved, undid and re-approved a shortlist
- [ ] Exported the audit log for a vacancy

## Recorded video outline (5 short videos, 3–5 min each)
Record on staging at 1280×720, synthetic data only, captions on, no real names on screen.

| # | Title | Script beats | Ends with |
|---|---|---|---|
| 1 | *Welcome: how MUDHOTECH HR RECRUITING SYSTEM helps you hire fairly* | the five rules; what the AI does (finds evidence, suggests a band) and what it never does (decide, reject, look at protected characteristics); where candidates see the AI notice | "Next: create your first vacancy" |
| 2 | *Create a vacancy and its rubric* | wizard steps; weights; essentials need a reason; the protected-topic checker; approval and publishing; versions are fixed once used | a published vacancy on the job board |
| 3 | *Review applications with evidence* | bands are hints; filters and saved views; blind review and reveal-with-reason; the evidence viewer; flags; verify / clarify; j/k navigation | a verified claim and a clarification sent |
| 4 | *Build and approve a shortlist* | AI pre-fill; decide with reasons; submit; approve; notification delay and undo; candidates notified | approved shortlist, emails queued |
| 5 | *Oversight, audit and privacy* | dashboard and override analytics; audit export; reconstruct PDF; AI on/off; privacy requests | "Help is one click away" (support contacts) |

## After the session
- Send the attendees: links to the role guides, the support contacts, the feedback form.
- Facilitator notes go to the pilot log (questions asked, confusing screens) → backlog review weekly.
