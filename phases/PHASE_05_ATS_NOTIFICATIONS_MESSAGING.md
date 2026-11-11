# PHASE 05 — ATS Workflow, Notifications & Messaging

**Release:** MVP · **Modules:** M13, M14, M23 · **Depends on:** Phase 04
**Read first:** `docs/01 M13, M14, M23`, `docs/03 notifications/messaging`, `docs/04 Notifications & messaging`, `docs/07 H`

## Goal
Reliable, templated, deduplicated communications (email + in-app), structured clarification requests and secure
message threads, plus a full applicant-tracking pipeline UI over the state machine.

## Tasks
- [x] **P05-T01** — `apps.notifications` models: NotificationTemplate (platform defaults + org overrides, versioned), Notification (dedupe_key unique), EmailSuppression; template renderer (Jinja2 sandboxed or Django template with strict variables), markdown→HTML email layout (branded, plain-text alternative), variable validation on save, preview endpoint.
- [x] **P05-T02** — Default templates (en): application_received, document_rejected_reupload, clarification_requested, clarification_reminder, application_withdrawn_confirmation, draft_deadline_reminder, draft_abandoned, shortlisted, not_selected (respectful, no scores), recruitment_paused, invitation_staff, rights_request_update, recruiter_digest (new applications/processing done). No sensitive data in emails (EC-NOT rules).
- [x] **P05-T03** — Delivery pipeline: outbox consumers → `send_notification` task (notifications queue) → provider backend (SMTP/SES via django-anymail or SMTP) with retries (backoff to 24 h), dead letter, suppression check, quiet hours for candidate non-urgent (07:00–20:00 candidate TZ) (EC-NOT-09), dedupe (EC-NOT-03), withdrawn/anonymised suppression (EC-NOT-04).
- [x] **P05-T04** — SES/SMTP bounce & complaint webhook endpoint (SNS signature verification) → suppression + in-app banner to update email (EC-NOT-01). Dev: Mailpit.
- [x] **P05-T05** — In-app notifications API (list, unread count, mark read/all) + `NotificationBell` component with polling (30 s) or SSE.
- [x] **P05-T06** — `apps.messaging`: ClarificationRequest (templates + free text + optional upload, due_at), candidate answer endpoint (answers stored as candidate-reported evidence → outbox `clarification.answered`), expiry task (EC-NOT-07); MessageThread/Message with sanitised bodies, attachments via documents scan (EC-NOT-08), read tracking; all tenant-scoped & audited; status transitions `needs_information` ↔ `processing/under_review` wired to state machine.
- [x] **P05-T07** — ATS features: notes (@mentions → in-app notification), tags, assign recruiter, reopen with reason, holds; HR transition endpoint with reason codes (`decision_reasons` seed list).
- [x] **P05-T08** — Frontend HR: pipeline kanban view per vacancy (columns = statuses; drag triggers reason modal + server validation; illegal moves rejected with message), application timeline component, notes/tags/assign UI, clarification request composer (templates), message thread panel.
- [ ] **P05-T09** — Frontend candidate: actions-needed panel (clarifications, re-uploads), clarification answer form, messages inbox per application, notification centre.
- [ ] **P05-T10** — HR settings: template editor (markdown with variable picker, preview with sample data, version history, revert to default).
- [ ] **P05-T11** — No-reply auto-response doc + `Reply-To` handling decision (EC-NOT-06): emails link to portal messages.

## Edge cases
EC-NOT-01..09, EC-REV-07 (suppression part), EC-ACC-07 (notify verified email only).

## Exit criteria
- [ ] Killing the worker mid-send and replaying events never sends duplicates (test).
- [ ] Clarification round-trip works end to end (HR → candidate → answer → HR notified).
- [ ] Kanban rejects invalid transitions; every move audited.
