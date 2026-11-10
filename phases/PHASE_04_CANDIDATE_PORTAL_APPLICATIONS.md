# PHASE 04 — Candidate Portal, Documents, Applications & Questionnaires

**Release:** MVP · **Modules:** M06, M07, M08 (answering), documents · **Depends on:** Phase 03
**Read first:** `docs/01 M06–M08 & §3.3`, `docs/02 §5.1`, `docs/03 candidates/documents/applications/questionnaires`, `docs/04 Candidate & Applications`, `docs/06 §3`, `docs/07 D`, `docs/08 §3.1`

## Goal
Candidates build a profile, upload CVs safely, complete a resumable 6-step application with job-specific questions,
and submit exactly once — with an immediate reference number — regardless of later processing outcomes.

## Tasks
- [x] **P04-T01** — `apps.candidates`: profile + experiences/educations/certifications/skills/languages models & CRUD APIs; completeness score; **no protected fields** (test asserts model has none of the forbidden field names).
- [x] **P04-T02** — `apps.documents`: UploadSession + Document models; presign flow (`upload-sessions`, `complete`), direct-upload fallback; validation: declared type allow-list per purpose, size limits (configurable per org/purpose), filename sanitisation; download endpoint (permission-checked, 60 s presigned GET, access log).
- [x] **P04-T03** — Scan pipeline (documents queue): magic-byte detection (`python-magic` + custom DOCX/PDF checks), DOCX zip-bomb guard, PDF page count/encryption check, ClamAV `INSTREAM` scan, promote quarantine→documents bucket, `scan_status` updates, outbox `document.accepted|rejected`; candidate notified on rejection. Fake ClamAV in tests + EICAR test string integration test (nightly with real clamd).
- [x] **P04-T04** — Orphan cleanup beat task (upload sessions expired, objects in quarantine > 24 h) (EC-APP-08); sha256 dedupe per user (EC-DOC-25).
- [x] **P04-T05** — `apps.applications` models: Application (+ reference counter table), ApplicationDocument, ApplicationStatusEvent, QuestionResponse usage; duplicate policy enforcement (`active_key` partial unique index + service checks) (EC-APP-02/03).
- [x] **P04-T06** — Application state machine module `applications/state_machine.py` implementing **all** transitions from SRS §3.3 with guards (human-required set), used by a single `transition(application, to, actor, reason)` service with `select_for_update`, status event, audit, outbox `application.status_changed`. Exhaustive transition tests.
- [x] **P04-T07** — Draft APIs: create/resume draft, autosave PATCH with lock_version, attach documents by role, bulk upsert answers (validation per question type, branching visibility respected server-side — hidden answers discarded), review summary endpoint (missing required items list).
- [x] **P04-T08** — Submit service: `@idempotent`, `atomic`, checks (email verified, job published & before deadline in job TZ, org active, required docs attached (scan pending allowed; infected not), required visible questions answered, consents), freeze `candidate_profile_snapshot` + job_version, assign reference `MHRS-<ORGCODE>-<YYYY>-<NNNNNN>`, status `submitted`, outbox `application.submitted`, receipt notification. Load test helper for 100 concurrent submits (EC-APP-01).
- [x] **P04-T09** — Withdraw service (any non-terminal state; stops processing via status check in tasks; recruiter notification) (EC-APP-12/13); abandoned-draft beat task at deadline + email (EC-JOB-08/09/10 interplay).
- [x] **P04-T10** — Consent records: application processing consent + AI-assisted screening notice version stored on submit; `/how-we-use-ai` content page; objection option recorded (`objects_to_automated_processing` → used in Phase 7/8).
- [ ] **P04-T11** — Assisted application (staff creates on behalf; candidate invited; flag + consent captured) (EC-APP-17).
- [ ] **P04-T12** — Frontend `FileUploader` (presign → PUT with progress → complete → poll scan status; retry/renew on failure; cancel; accessible).
- [ ] **P04-T13** — Frontend candidate: `/candidate/dashboard`, `/candidate/profile` (sections + completeness), `/candidate/documents` (CV library, set default), `/candidate/applications` + detail (timeline, withdraw), `/candidate/settings`.
- [ ] **P04-T14** — Frontend `/apply/[jobId]` wizard per `docs/08 §3.1`: autosave indicator, resume at last step, conditional questions (aria-live), word counters, error summary, review step (extracted-data panel placeholder until Phase 6), consent, submit with idempotency key, confirmation page; handles `deadline_passed`, `duplicate_application`, `org_suspended`, session expiry (EC-APP-06/14/19/20).
- [ ] **P04-T15** — HR minimal list: `/hr/jobs/[id]/applications` basic table (status, submitted at, candidate name) + application detail read-only (documents viewer via download, answers) — full review UI in Phase 8.
- [ ] **P04-T16** — E2E: candidate registers → verifies (Mailpit API) → applies with CV + answers → receives receipt; withdraw flow; duplicate attempt.

## Edge cases
EC-APP-01..23 (EC-APP-15/16 flags computed in Phase 6), EC-DOC-04..08, EC-DOC-25, EC-ACC-03, EC-OPS-02.

## Exit criteria
- [ ] 100 concurrent submissions (Locust/pytest-xdist script) → 100 applications, 0 duplicates, all receipts queued.
- [ ] Infected (EICAR) and spoofed files rejected; application retained when a document fails.
- [ ] Wizard usable on 360 px wide mobile viewport and with keyboard only; axe: no serious violations.
- [ ] State machine exhaustive tests pass.
