# 04 — API Contract (REST, `/api/v1/`)

## 1. Conventions
- JSON, snake_case fields, UUID ids, ISO-8601 UTC timestamps (`2026-11-08T10:00:00Z`).
- Auth: session cookie (allauth headless) + `X-CSRFToken` on unsafe methods. Public endpoints marked 🌐.
- Org context: header `X-Org-Id` for staff endpoints (validated against membership); otherwise session active org.
- Pagination: `?page=&page_size=` (default 25, max 100) → `{count, next, previous, results}`; cursor pagination for large tables (`applications`, `audit`) → `{next_cursor, results}`.
- Filtering: `?status=&search=&ordering=-submitted_at`.
- Idempotency: `Idempotency-Key` header (UUID) **required** on: application submit, shortlist approve, offer issue, payment initiate, export create. Same key + same body → same response (24 h).
- Optimistic concurrency: resources with `lock_version` require it in PATCH body; mismatch → 409 `conflict.stale_version`.
- Rate limits: auth endpoints 10/min/IP; public search 60/min/IP; uploads 30/h/user; general 300/min/user.
- Versioning: breaking changes → `/api/v2`. Additive changes allowed in v1.

### Error envelope
```json
{ "error": { "code": "validation_error", "message": "Some fields are invalid.",
  "details": { "closes_at": ["Must be in the future."] }, "request_id": "req_01J..." } }
```
Codes: `validation_error`(400) · `not_authenticated`(401) · `mfa_required`(401) · `permission_denied`(403) · `not_found`(404, also used for cross-tenant) · `conflict.*`(409: `stale_version`, `invalid_transition`, `duplicate_application`, `already_processed`) · `gone`(410) · `payload_too_large`(413) · `unsupported_media_type`(415) · `rate_limited`(429) · `org_suspended`(423) · `deadline_passed`(422) · `internal_error`(500).

## 2. Endpoints

### Auth & account (allauth headless under `/api/v1/auth/browser/v1/...` wrapped/documented)
| Method | Path | Who | Notes |
|---|---|---|---|
| POST | /auth/signup | 🌐 | candidate signup; sends verification |
| POST | /auth/login | 🌐 | returns flows incl. `mfa_authenticate` |
| DELETE | /auth/session | user | logout |
| POST | /auth/email/verify | 🌐 | key |
| POST | /auth/password/request · /auth/password/reset | 🌐 | generic responses |
| GET/POST/DELETE | /auth/mfa/authenticators… | user | TOTP, recovery codes |
| GET | /me | user | user, memberships (org, role), platform_role, candidate_profile_id, active_org |
| PATCH | /me | user | names, phone, locale, timezone |
| GET/DELETE | /me/sessions[/{id}] | user | list/revoke |
| POST | /me/active-org | staff | switch org |

### Organisations & team
| Method | Path | Who |
|---|---|---|
| POST | /organisations | user (becomes org_admin) |
| GET/PATCH | /organisations/{id} | member / org_admin |
| GET/PATCH | /organisations/{id}/policies | org_admin (hr_manager read) |
| CRUD | /organisations/{id}/departments, /locations | org_admin, hr_manager |
| GET | /organisations/{id}/members | org_admin, hr_manager |
| PATCH/DELETE | /organisations/{id}/members/{membership_id} | org_admin |
| POST | /organisations/{id}/invitations · POST …/{inv}/resend · DELETE …/{inv} | org_admin |
| GET | 🌐 /invitations/{token} · POST /invitations/{token}/accept | invitee |
| GET | 🌐 /companies/{slug} | public profile + open jobs |

### Taxonomy
| GET | /taxonomy/skills?search= | staff/candidate (autocomplete) |
| GET | /taxonomy/qualification-levels | any |
| CRUD | /organisations/{id}/custom-skills | hr_manager |
| CRUD | /platform/taxonomy/* | platform_admin |

### Jobs
| Method | Path | Who | Notes |
|---|---|---|---|
| GET | 🌐 /jobs | public | published only; filters q, location, workplace_type, employment_type, org, posted_within, closing_within |
| GET | 🌐 /jobs/{slug-or-id} | public | published or recently closed |
| GET | 🌐 /jobs/{id}/questions | public/candidate | approved questionnaire of published version |
| GET | /hr/jobs | staff | all states, assigned filter |
| POST | /hr/jobs | recruiter+ | create draft |
| GET/PATCH | /hr/jobs/{id} | assigned | PATCH needs lock_version |
| PUT | /hr/jobs/{id}/criteria | assigned | replace criteria list of draft version |
| PUT | /hr/jobs/{id}/rubric | assigned | weights validated |
| PUT | /hr/jobs/{id}/questionnaire | assigned | questions + branching + scoring |
| POST | /hr/jobs/{id}/lint | assigned | returns publish-readiness checklist + prohibited-question warnings |
| POST | /hr/jobs/{id}/submit-for-approval | recruiter+ | |
| POST | /hr/jobs/{id}/approve · /reject | hr_manager (≠ submitter if dual control) | |
| POST | /hr/jobs/{id}/publish · /schedule · /pause · /resume · /close · /archive · /extend-deadline · /duplicate | hr_manager / assigned | each writes job_event + audit |
| POST | /hr/jobs/{id}/new-version | hr_manager | creates draft version from published |
| POST | /hr/jobs/{id}/ai-suggestions | assigned | criteria/question suggestions (flag) |
| GET/PUT | /hr/jobs/{id}/assignments | hr_manager | |

### Candidate profile & documents
| GET/PATCH | /candidate/profile | candidate |
| CRUD | /candidate/profile/experiences, /educations, /certifications, /skills, /languages | candidate |
| POST | /documents/upload-sessions | user | {purpose, filename, mime, size} → {id, url, headers, expires_at} |
| POST | /documents/upload-sessions/{id}/complete | user | |
| POST | /documents/direct-upload | user | multipart fallback |
| GET | /documents/{id} | owner/authorised staff | metadata + scan status |
| GET | /documents/{id}/download | owner/authorised staff | 302 to short-lived presigned GET (60 s); logs access |
| GET | /candidate/resumes · POST /candidate/resumes/{doc_id}/set-default | candidate |
| GET | /candidate/resumes/{doc_id}/extraction | candidate | parsed claims |
| POST | /candidate/claims/{claim_id}/corrections | candidate |
| POST | /candidate/resumes/{doc_id}/import-to-profile | candidate | prefill with confirmation |

### Applications (candidate side)
| POST | /applications | candidate | {job_id} → draft (or existing draft returned; duplicate policy) |
| GET | /applications | candidate | own list |
| GET/PATCH | /applications/{id} | owner | autosave draft fields (lock_version) |
| PUT | /applications/{id}/documents | owner | attach docs by role |
| PUT | /applications/{id}/answers | owner | bulk upsert answers (partial ok in draft) |
| GET | /applications/{id}/review | owner | pre-submit validation summary + extracted data |
| POST | /applications/{id}/submit | owner | **Idempotency-Key**; 201 {reference, submitted_at} ; 422 deadline_passed; 409 duplicate_application |
| POST | /applications/{id}/withdraw | owner | |
| GET | /applications/{id}/timeline | owner | candidate-safe events only |
| GET/POST | /applications/{id}/clarifications[/{cid}/answer] | owner | |
| GET/POST | /applications/{id}/messages | owner | |

### HR applications, screening, review
| GET | /hr/jobs/{id}/applications | assigned | filters: status, band, min_score, coverage_lt, flags, criteria_met, search, tag; cursor |
| GET | /hr/applications/{id} | assigned | full detail (blind mode redaction server-side when enabled) — logs access |
| POST | /hr/applications/{id}/transition | assigned | {to_status, reason_code, reason_text} validated by state machine |
| POST | /hr/applications/{id}/notes · GET notes | assigned | |
| POST | /hr/applications/{id}/assign | hr_manager | |
| POST | /hr/applications/{id}/clarifications | recruiter+ | |
| GET | /hr/applications/{id}/evaluations | assigned | versions list |
| GET | /hr/evaluations/{id} | assigned | criterion results + evidence |
| GET | /hr/evaluations/{id}/evidence | assigned | evidence with snippets, page refs |
| POST | /hr/claims/{id}/verify | recruiter+ | confirm/correct/reject → human_verifications; triggers re-eval option |
| POST | /hr/jobs/{id}/screening-runs | hr_manager / recruiter | {scope: all|pending|failed|selected, application_ids?, reason} |
| GET | /hr/jobs/{id}/screening-runs[/{run}] | assigned | progress counts |
| POST | /hr/applications/{id}/retry-processing | recruiter+ | |
| GET | /hr/compare?ids=a,b,c | assigned | ≤4 |

### Shortlisting
| GET/POST | /hr/jobs/{id}/shortlists | assigned | create proposal {desired_size} → pre-filled suggestions (not decisions) |
| PATCH | /hr/shortlists/{id}/entries | assigned | set decisions + reasons (draft) |
| POST | /hr/shortlists/{id}/submit | recruiter+ | → pending_approval |
| POST | /hr/shortlists/{id}/approve · /reject | hr_manager (dual control rules) | **Idempotency-Key**; applies transitions atomically; schedules notifications after delay |
| POST | /hr/shortlists/{id}/undo | approver | within notification delay window |
| GET | /hr/decision-reasons | staff | |

### Notifications & messaging
| GET | /notifications · POST /notifications/{id}/read · POST /notifications/read-all | user |
| CRUD | /hr/notification-templates · POST …/{id}/preview | org_admin/hr_manager |
| GET/POST | /hr/applications/{id}/messages | assigned |

### Dashboard & reports
| GET | /hr/dashboard/summary?department=&from=&to= | staff |
| GET | /hr/jobs/{id}/funnel | assigned |
| GET | /hr/reports/recruitment | hr_manager | (v1.1 advanced) |
| POST | /hr/exports · GET /hr/exports/{id} | hr_manager | async; download link expires 15 min |

### Privacy & audit
| GET/POST | /privacy/consents | user |
| POST | /privacy/requests · GET /privacy/requests | user |
| GET/PATCH | /hr/privacy/requests[/{id}] | org_admin |
| GET | /hr/audit-events?target_type=&target_id=&actor=&action=&from=&to= | auditor, org_admin |
| GET | /hr/applications/{id}/reconstruct | auditor, hr_manager | full decision reconstruction bundle |
| CRUD | /hr/legal-holds | org_admin |

### Platform admin
| GET/PATCH | /platform/organisations[/{id}] · POST …/verify · /suspend · /reactivate | platform_admin |
| GET | /platform/health · /platform/queues · /platform/dead-letters · POST …/{id}/retry | platform_admin |
| POST | /platform/support-access · DELETE …/{id} | platform_admin (reason, expiry ≤ 4h) |
| CRUD | /platform/feature-flags, /platform/plans, /platform/model-registry | platform_admin |

### v1.1 / v1.2
`/hr/interviews`, `/hr/interviews/{id}/scorecards`, `/candidate/interviews/{id}/book`, `/hr/offers`, `/hr/offers/{id}/approve|issue|withdraw`, `/candidate/offers/{id}/accept|decline`, `/hr/talent-pool`, `/candidate/talent-pool/consent`, `/billing/subscription`, `/billing/invoices`, `/billing/payments/paynow/initiate`, `/billing/payments/paynow/result` (🌐 webhook, hash-verified), `/hr/webhooks`, `/hr/api-keys`, `/public-api/v1/jobs` (API key).

## 3. Health
`GET /healthz` (process alive) · `GET /readyz` (DB, Redis, S3 reachable) — no auth, no details leaked.

## 4. Async events (outbox `event_type`)
| Event | Producer | Consumers |
|---|---|---|
| `document.uploaded` | documents | scan task |
| `document.accepted` / `document.rejected` | scan task | applications (unblock processing), notifications (reject → candidate) |
| `application.submitted` | applications | processing orchestrator, notifications (receipt), analytics |
| `resume.extraction_succeeded` / `_failed` | resumes | orchestrator, notifications (re-upload request on failure types) |
| `application.evidence_ready` | orchestrator | screening.evaluate |
| `screening.completed` / `screening.failed` | screening | applications (→ under_review / processing_error), notifications (recruiter digest) |
| `clarification.requested` / `.answered` | messaging | notifications / screening re-eval |
| `shortlist.approved` | shortlisting | applications transitions done in-tx; notifications (delayed) |
| `application.status_changed` | applications | notifications (per template rules), analytics, webhooks(v1.2) |
| `job.published` / `job.closed` | jobs | sitemap/feed, draft-holders notification, analytics |
| `rights_request.created` | privacy | notifications to org_admin |
| `notification.failed` | notifications | retry / suppression / escalation |
| `retention.due` | beat | privacy anonymiser |

Payloads carry IDs + minimal data only (no CV text, no PII beyond ids).
