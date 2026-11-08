# 02 — Architecture

## 1. Style
**Modular monolith** (Django) + **independently scalable Celery worker pools** + Next.js frontend.
Domains are separate Django apps with explicit service interfaces; the AI engine is a pure-Python package
(`backend/ai_engine`) with no Django imports in its core (adapters live in `apps/screening`), so it can be
extracted to a separate service later without rewrites.

```
                 ┌──────────────── Browser (mobile-first) ────────────────┐
                 │  Public job board · Candidate portal · HR · Admin       │
                 └───────────────┬────────────────────────────────────────┘
                                 │ HTTPS (Nginx, TLS, HSTS, rate limits)
                 ┌───────────────▼──────────────┐
                 │ Next.js (App Router, SSR/RSC)│  rewrites /api/* → Django (same-origin cookies)
                 └───────────────┬──────────────┘
                                 │
                 ┌───────────────▼──────────────┐      ┌───────────────┐
                 │ Django + DRF (gunicorn/uvicorn)│────▶│ PostgreSQL 16 │ (+pgvector, pg_trgm)
                 │ auth · orgs · jobs · apps ·   │      └───────────────┘
                 │ screening · shortlist · audit │      ┌───────────────┐
                 │ outbox writer                 │────▶│ S3 / MinIO    │ (private, SSE, presigned)
                 └───────────────┬──────────────┘      └───────────────┘
                                 │ outbox relay (beat, every 2s) → Redis broker
     ┌───────────────┬───────────┼───────────────┬──────────────┐
     ▼               ▼           ▼               ▼              ▼
 worker:documents worker:ai  worker:notifications worker:reports  beat (schedules)
 (scan, extract,  (match,    (email, in-app,     (exports,        (deadlines, retention,
  OCR; sandboxed) evaluate,   SMS/WA later)       analytics)       outbox relay, cleanup)
                  explain)
     │               │
     ▼               ▼
  ClamAV (clamd)  Embedding model (local, CPU) · optional LLM provider adapter (redacted input)
```

## 2. Components
| Component | Tech | Notes |
|---|---|---|
| Reverse proxy | Nginx | TLS (Certbot), gzip/brotli, `client_max_body_size 30m` (only for fallback upload path), security headers, rate limit zones for `/api/v1/auth/*` |
| Frontend | Next.js, TS, Tailwind, shadcn/ui | RSC for public pages (SEO), client components for wizards/dashboards; TanStack Query for client data |
| API | Django 5.2 LTS, DRF, drf-spectacular | ASGI via uvicorn workers under gunicorn; session auth (allauth headless) + CSRF |
| DB | PostgreSQL 16 | UUID PKs, tenant indexes, FTS, pgvector for skill/role embeddings |
| Broker/cache | Redis 7 | Celery broker (DB 0), cache & rate limits (DB 1), locks (DB 2) |
| Workers | Celery 5 | Queues: `default`, `documents`, `ai`, `notifications`, `reports`; `worker_prefetch_multiplier=1`, `acks_late=True`, `task_reject_on_worker_lost=True`, soft/hard time limits |
| Scanner | ClamAV daemon | Separate container; `documents` worker calls via TCP |
| OCR | Tesseract 5 (eng) | Inside documents worker image |
| Storage | S3 (prod) / MinIO (dev) | Buckets: `mhrs-uploads-quarantine`, `mhrs-documents` (clean), `mhrs-exports` (expiring), `mhrs-public` (logos) |
| Email | SES/SMTP (prod), Mailpit (dev) | Via notifications outbox |
| Monitoring | Sentry, Flower (internal), Prometheus exporters optional, uptime checks | JSON logs to stdout → CloudWatch agent |

## 3. Backend apps
| App | Responsibility |
|---|---|
| `core` | BaseModel, TenantModel/Manager, outbox, idempotency, error envelope, pagination, request_id middleware, health checks, feature flags |
| `accounts` | User model (email login), allauth config, MFA, sessions, platform roles |
| `organisations` | Org, departments, locations, policies, memberships, invitations, org context middleware |
| `jobs` | Vacancy, JobVersion, Criterion, Rubric, approvals, publishing, public listing, FTS |
| `taxonomy` | Skills, aliases, relations, qualification levels/equivalences, versioning |
| `candidates` | CandidateProfile, experience, education, skills, CV library, corrections |
| `questionnaires` | Questions, options, branching, rubrics, question bank, prohibited-question linter |
| `applications` | Application, drafts, documents, submission, status machine, withdrawals, references |
| `documents` | Upload sessions, presign, scan, storage moves, file metadata |
| `resumes` | Extraction runs, extracted claims, evidence (Django side of ai_engine.extraction) |
| `screening` | Screening runs, evaluations, criterion results, evidence links, explanations, re-evaluation |
| `shortlisting` | Review lists, shortlist proposals, approvals, decisions, overrides |
| `messaging` | Clarification requests, threads, messages |
| `notifications` | Templates, outbox consumers, delivery logs, in-app notifications, suppression |
| `analytics` | Dashboard selectors, reports, exports |
| `audit` | AuditEvent (hash-chained), access logs, reconstruct service |
| `privacy` | Consents, rights requests, retention policies & jobs, legal holds |
| `interviews` (v1.1) | Interviews, slots, panels, scorecards |
| `offers` (v1.1) | Offers, approvals, letters, hire records |
| `talentpool` (v1.1) | Pool memberships, consent, searches |
| `billing` (v1.1) | Plans, subscriptions, usage, invoices, Paynow |
| `integrations` (v1.2) | Webhooks, API keys, calendar, SMS/WhatsApp |
| `platform` | Platform admin: tenants, health, break-glass |

## 4. ai_engine package
```
ai_engine/
  contracts.py        # pydantic models: DocumentText, ExtractedClaim, CandidateEvidence, Criterion, CriterionResult, Evaluation
  extraction/         # pdf.py, docx.py, ocr.py, quality.py, sections.py, parser.py (rules+spaCy), dates.py, contacts.py, pii.py
  normalisation/      # skills.py (taxonomy lookup), titles.py, qualifications.py, experience.py (overlap merge)
  matching/           # rules.py, skills_match.py, semantic.py (embeddings), experience_match.py, answers.py, conflicts.py
  evaluation/         # scoring.py (weighted formula), coverage.py, bands.py, rubric.py
  explanations/       # templates.py, grounding.py (citation validator), clarifications.py
  llm/                # provider.py (interface), anthropic_adapter.py, openai_adapter.py, null_adapter.py, redaction.py, prompts/ (versioned), schemas.py
  versioning.py       # ENGINE_VERSION, hashing of inputs
  tests/              # golden tests with synthetic CVs
```

## 5. Key flows

### 5.1 Upload & submit
1. Client `POST /api/v1/documents/upload-sessions/` → server validates declared type/size, creates `UploadSession`, returns presigned PUT URL to **quarantine bucket** (expires 10 min).
2. Client PUTs file directly to S3 (retry on failure); then `POST /upload-sessions/{id}/complete/`.
3. Server verifies object exists/size, emits `document.uploaded` (outbox). Worker: magic bytes → ClamAV → move to clean bucket → `document.accepted` or `document.rejected` (candidate sees status within seconds).
4. `POST /api/v1/applications/{id}/submit/` with `Idempotency-Key` → transaction: validate required answers/docs (docs may still be `scanning` → allowed; scanning continues), set `submitted`, reference number, status event, audit, outbox `application.submitted` → 201 receipt.
5. Fallback path when presigned upload is blocked: multipart upload through API (`/documents/direct-upload/`).

### 5.2 Processing
`application.submitted` → (wait for docs accepted) → `resume.extract` (documents queue) → `application.evidence_ready` → `screening.evaluate` (ai queue) → `screening.completed` → status `under_review` + notify recruiter digest.
Each step writes run records with status, timings, versions, errors. Retries: 3 with backoff (30 s, 2 min, 10 min); then `processing_error` + flagged in HR queue with "Retry" and "Review manually".

### 5.3 Transactional outbox
`outbox_events(id, event_type, aggregate_type, aggregate_id, payload jsonb, dedupe_key unique, status, attempts, available_at, created_at, published_at)`.
Writers insert inside the business transaction. Relay task (beat every 2 s + `on_commit` kick) selects `FOR UPDATE SKIP LOCKED`, publishes Celery tasks, marks `published`. Consumers are idempotent via `processed_events(consumer, event_id)` unique.

### 5.4 Tenancy
- `OrganisationContextMiddleware` resolves `request.organisation` from header `X-Org-Id` **validated against memberships** (or session active org). Never from body.
- `TenantManager.for_org(org)`; default manager on TenantModel raises if unscoped queryset is evaluated in request context (dev/test strict mode) — implemented via a guard queryset.
- DRF base viewset `TenantScopedViewSet` applies scoping + object permissions; tests generated per endpoint for cross-tenant 404.
- Phase 9 hardening option: PostgreSQL Row-Level Security with `SET app.current_org` (ADR-012).

### 5.5 Authentication
django-allauth **headless** (browser client): session cookie (HttpOnly, Secure, SameSite=Lax), CSRF cookie + header `X-CSRFToken`. Next.js uses same origin via rewrites, so no tokens in JS storage. MFA via `allauth.mfa` (TOTP + recovery codes). Staff SSO (Google/Microsoft) in v1.2 via allauth socialaccount.

## 6. Environments
| Env | Purpose | Infra |
|---|---|---|
| dev | Local (Windows + Docker Desktop) | docker-compose: postgres, redis, minio, mailpit, clamav, backend, worker(s), beat, frontend, flower |
| test/CI | GitHub Actions | service containers postgres/redis; ClamAV mocked except nightly |
| staging | Pre-prod, seeded synthetic data | EC2 (t3.large) docker compose; S3 staging buckets; SES sandbox |
| prod | Live | EC2 (t3.xlarge or m6i.large+) docker compose (or later ECS), RDS PostgreSQL (recommended) or self-managed with backups, S3, SES, CloudWatch, Sentry |

## 7. Repository structure (detailed)
```
backend/
  config/ settings/{base,dev,test,staging,prod}.py urls.py asgi.py wsgi.py celery.py
  apps/<app>/ models.py services.py selectors.py permissions.py tasks.py events.py admin.py api/{serializers,views,urls,filters}.py tests/
  ai_engine/ (see §4)
  fixtures/ synthetic_cvs/ taxonomy/ qualifications/
  requirements/{base,dev,prod,ai}.txt   (or pyproject with uv)
  Dockerfile  Dockerfile.worker  manage.py  pyproject.toml  pytest.ini
frontend/
  src/app/(public)/ (candidate)/candidate/ (hr)/hr/ (admin)/admin/ apply/[jobId]/ api-proxy config
  src/features/{auth,organisations,jobs,candidates,applications,questionnaires,screening,shortlisting,messaging,notifications,reports,admin}
  src/components/{ui,layout,forms,data-table,evidence-viewer}
  src/lib/{api-client.ts,auth.ts,csrf.ts,format.ts,i18n.ts}  src/types/api.d.ts
  tests/ e2e/ (Playwright)  messages/en.json
infrastructure/
  docker/ nginx/ deployment/{ec2-bootstrap.sh, deploy.sh, backup.sh, restore.sh} monitoring/
scripts/ dev-up.ps1 dev-up.sh seed.ps1 seed.sh
.github/workflows/ ci.yml deploy-staging.yml deploy-prod.yml nightly.yml
```
