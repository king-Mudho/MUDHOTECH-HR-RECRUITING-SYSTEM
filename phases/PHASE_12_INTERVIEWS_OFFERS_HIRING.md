# PHASE 12 — Interviews, Offers & Hiring

**Release:** v1.1 · **Modules:** M16, M17 · **Depends on:** Phase 11 (MVP live)
**Read first:** `docs/01 M16–M17`, `docs/03 v1.1 interviews/offers`, `docs/07 L`

## Tasks
- [ ] **P12-T01** — `apps.interviews` models: Interview, InterviewSlot, InterviewPanelist, Scorecard (+ scorecard templates derived from job criteria/competencies).
- [ ] **P12-T02** — Scheduling services: create interview (mode, stage, panel), offer slots, candidate self-booking (row-locked slots), reschedule/cancel with reasons, conflict detection for panelists (EC-INT-01), timezone-aware (EC-INT-02), ICS generation (UTC + TZID), reminders (24 h, 1 h), no-show handling (EC-INT-03); transitions `shortlisted → interview`.
- [ ] **P12-T03** — Scorecards: per-criterion 1–5 with evidence notes, overall recommendation; independent submission (others hidden until own submitted) (EC-INT-04); AI scores hidden from panelists per policy (ADR-019); consolidated view for HR.
- [ ] **P12-T04** — `apps.offers`: Offer, OfferApproval, HireRecord; approval chain; letter template (DOCX/PDF generation via HTML→PDF (WeasyPrint)), issue via portal, candidate accept (typed name + checkbox + timestamp + IP truncated) / decline with reason, expiry task (EC-OFF-02), withdraw; block issue without approvals (EC-OFF-01); openings counter & over-acceptance warning (EC-OFF-03); accept-then-withdraw (EC-OFF-04).
- [ ] **P12-T05** — Hiring close-out: hire record, prompt to close vacancy when openings filled, bulk final notifications to remaining candidates **only after human confirmation** with reasons.
- [ ] **P12-T06** — APIs + permission matrix + cross-tenant tests for all new endpoints.
- [ ] **P12-T07** — Frontend HR: `/hr/interviews` calendar/list (day/week), schedule dialog, panel management, scorecard form, consolidated feedback; `/hr/offers` list, offer builder, approvals, letter preview.
- [ ] **P12-T08** — Frontend candidate: interview invitations (book slot, add to calendar, reschedule request), offer view (accept/decline), timeline updates.
- [ ] **P12-T09** — Notifications templates: interview_invitation, interview_reminder, interview_rescheduled, interview_cancelled, offer_issued, offer_expiring, offer_accepted (HR), offer_declined (HR), hired_welcome (optional).
- [ ] **P12-T10** — Funnel extended to interviews/offers/hires on dashboard.

## Exit criteria
- [ ] E2E: shortlisted → interview booked → scorecards → offer approved → issued → accepted → hired; vacancy closed.
- [ ] EC-INT-01..04 and EC-OFF-01..04 tested.
