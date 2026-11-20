# 11 — Decisions Log (ADRs & defaults)

Status: **Accepted** = implement as written · **OWNER-DECISION** = default applies for development; owner confirms before production (agent must NOT block development on these, only on go-live gates).

| ID | Decision | Status | Rationale |
|---|---|---|---|
| ADR-001 | Modular monolith (Django) + Celery worker pools; ai_engine as framework-free package | Accepted | Simpler to build/secure; extractable later |
| ADR-002 | Django 5.2 LTS, Python 3.12; verify newer LTS at Phase 1 | Accepted | Support to Apr 2028 |
| ADR-003 | Next.js App Router + TS strict + Tailwind + shadcn/ui; latest stable major verified at Phase 1 | Accepted | Owner choice |
| ADR-004 | Auth: django-allauth headless, session cookies + CSRF, same-origin via Next.js rewrites; no JWT in browser storage | Accepted | Safer against XSS token theft; MFA built in |
| ADR-005 | Multi-tenant from day one; shared DB, `organisation_id` scoping + tests; RLS optional hardening (ADR-012) | Accepted | Blueprint recommendation |
| ADR-006 | Transactional outbox for all async side effects | Accepted | No lost events when Redis down |
| ADR-007 | Presigned direct-to-S3 uploads into quarantine bucket + ClamAV promote | Accepted | Scalability + security |
| ADR-008 | Deterministic hybrid matching (rules + taxonomy + local embeddings); LLM optional/off by default | Accepted | Explainability, cost, privacy |
| ADR-009 | Missing evidence = not assessable; coverage reported; no auto-reject bands | Accepted | Fairness principle |
| ADR-010 | Local embedding model `all-MiniLM-L6-v2` (fallback `bge-small-en-v1.5`), pgvector | Accepted | CPU-friendly, no data leaves server |
| ADR-011 | App-level field encryption (Fernet, key-id prefixed) for CV text and messages | Accepted | Defence in depth |
| ADR-012 | PostgreSQL RLS as Phase 9 hardening (evaluate; implement if overhead acceptable) | Accepted — implemented 2026-11-17 (P09-T07) | Second line of tenant defence. 19 major tenant tables have a `FORCE`d `tenant_isolation` policy active when staff requests set `app.current_org` (HR paths with `X-Org-Id`; reset after each request). Measured overhead on the applicants list query: none beyond noise (median 3.7 ms -> 3.2 ms, 1,200 rows, non-superuser role). Requires a non-superuser, non-BYPASSRLS application DB role (docs/10 §3.1) |
| ADR-013 | Blind review mode default ON for first-pass screening | Accepted | Bias reduction |
| ADR-014 | Notification delay/undo window default 15 min after shortlist approval | Accepted | Mistake recovery |
| ADR-015 | Billing via Paynow (EcoCash, OneMoney, cards) first; Stripe optional later | Accepted | Zimbabwe market |
| ADR-016 | Hosting AWS, EC2 Ubuntu + Docker Compose for pilot; RDS PostgreSQL | Accepted | Owner's existing practice |
| ADR-017 | English-only parsing in MVP; i18n-ready UI | Accepted | Scope |
| ADR-018 | Hash-chained append-only audit table | Accepted | Tamper evidence |
| ADR-019 | Interview panelists don't see AI scores by default | Accepted | Anchoring bias |
| ADR-020 | Package manager: `uv` for Python (pyproject), npm for frontend | Accepted | Speed, lockfiles |
| ADR-021 | Dev-only S3 emulator: **SeaweedFS** (`chrislusf/seaweedfs`, S3 gateway on :9000) + `amazon/aws-cli` bucket init, replacing MinIO in dev | Accepted (2026-11-08) | `minio/minio` and `minio/mc` images are no longer publicly pullable (Docker Hub/quay deny). Production remains AWS S3; app code uses plain boto3/S3 API so the emulator is swappable (RustFS is the fallback). |
| ADR-023 | Email verification **mandatory before login** (allauth `ACCOUNT_EMAIL_VERIFICATION="mandatory"`, auto-login on confirmation); submit endpoints still enforce `require_verified_email` | Accepted (2026-11-09) | allauth can only keep signup enumeration-free (EC-ACC-02, FR-M01-05) when verification is mandatory. Trade-off: unverified users cannot log in to draft (EC-ACC-03 drafting case) — they verify first, which is one click from the signup email |
| ADR-024 | **No-reply email** (EC-NOT-06): all notification email is sent from `DEFAULT_FROM_EMAIL` (a `no-reply@` address) with **no `Reply-To`**; headers `Auto-Submitted: auto-generated` + `X-Auto-Response-Suppress: All`; every footer says replies are not read and links to the portal, where conversations happen in per-application message threads. In production the no-reply mailbox answers any reply once with the fixed auto-response in docs/10 §6 and keeps nothing (SES receipt rule) | Accepted (2026-11-11) | Message threads are tenant-scoped, audited and scanned; email replies would bypass all of that and leak personal data into an unmonitored mailbox |
| ADR-022 | Dev host ports are configurable via `*_HOST_PORT` env vars; defaults Postgres **15432** (was 55432 until 2026-11-09), Redis **6380** (others standard) | Accepted (2026-11-08, amended 2026-11-09) | Avoid clashes with other local Postgres/Redis instances; 55432 fell inside a Windows/Hyper-V reserved dynamic port range after a reboot, so defaults stay below 49152. Container-internal ports unchanged |
| ADR-025 | ADR-010 implementation: sentence-transformers + **CPU-only PyTorch** (`download.pytorch.org/whl/cpu` on Linux) as the optional `ml` extra, installed only in the worker image with `all-MiniLM-L6-v2` baked in (`HF_HUB_OFFLINE=1` at runtime); web image and CI unit tests use a deterministic hashing encoder; if the model cannot load, matching continues without the semantic component (EC-AI-06) | Accepted (2026-11-15) | Keeps the web image and CI small (no multi-GB CUDA wheels), no CV text or model calls leave the server, same model/stack as ADR-010 |
| ADR-026 | Optional LLM (docs/05 §9): provider interface with `null` default, Anthropic adapter on the official `anthropic` SDK (optional `llm` extra; model `claude-opus-5-5`, effort `low`, thinking left to the model since sampling params are not accepted - determinism via the (prompt hash, input hash, model) cache) and an OpenAI adapter whose SDK is installed only where an organisation chooses it; used only for re-phrasing grounded summaries and verbatim-checked section assist; refusals and any failure fall back to the deterministic templates (no server-side model fallback) | Accepted (2026-11-15) | Keeps scoring deterministic and auditable; the LLM can never add facts that are not cited evidence |
| ADR-027 | Frontend CSP without nonces: strict directives (`default-src 'self'`, `object-src 'none'`, `base-uri 'self'`, `form-action 'self'`, `frame-ancestors 'none'`, `connect-src 'self'`, `worker-src 'self' blob:`) but `script-src 'self' 'unsafe-inline'` (no `unsafe-eval` outside dev); API responses get `default-src 'none'` | Accepted (2026-11-17) | Next.js nonces require dynamic rendering of every page and are incompatible with Partial Prerendering / Cache Components that the public job board uses (Next.js CSP guide). Mitigations: React escaping, no untrusted HTML (nh3 allow-list server-side), same-origin API. Revisit with hash-based SRI when it leaves experimental |
| ADR-028 | Phase 10 calibration (P10-T03): listed-only skills score 75 (was 50), matching config `2026.11.2`; extraction semantic threshold 0.65 (was 0.75), engine `0.3.1`; evaluation semantic threshold stays 0.78 | Accepted (2026-11-17) | At 50 a skills-heavy vacancy rubric routed 12/44 gold-suitable CVs to lower match and an inferred match out-scored an explicit listed skill (D-008); 75 gives 100 % recall on corpus and vacancy rubrics with no unsuitable candidate recommended. Listed stays below used (100) and explanations say "listed among the skills". Extraction semantic matching added nothing at 0.75; 0.65 lifts equivalent-wording recall 0.738 -> 0.762 at unchanged precision. Evidence: docs/reports/AI_VALIDATION_REPORT.md, calibration_2026-11-17.md. Same release (P10-T04 fairness review): a foreign qualification verified by a person scores like a local one (100) instead of staying at 75 "needs verification" - otherwise "foreign" acted as a lasting proxy for origin. Existing evaluations keep their versions; HR opts in to re-evaluation |
| ADR-030 | Application status `offer -> not_selected` added (human decision with reason, `applications.decide`). Withdrawing an offer (P12-T04) does not change the application by itself; HR then either issues a new offer, reopens, or records `not_selected` | Accepted (owner, 2026-11-19) | Without it an application whose offer the employer withdrew could never reach an outcome; the candidate gets the respectful not-selected message only after a person decides |
| ADR-031 | Voluntary diversity monitoring (P13-T04) is **not built** in v1.1: the module stays off and absent until the owner enables it (decision D-10) | Accepted (2026-11-19) | The task is conditional on the owner enabling it and no decision exists. Collecting race, gender, disability or similar data conflicts with non-negotiable principle 7 unless there is a lawful basis (CDPA [Ch. 12:07] sensitive data) and counsel review (D-08). If enabled later: a separate optional form after submission, stored apart from applications, never visible to reviewers or the AI, aggregate-only reporting with k >= 10 suppression, its own consent purpose and retention |
| ADR-032 | SMS through a generic HTTP aggregator adapter (configurable base URL, bearer key, delivery receipts and STOP webhooks) and WhatsApp through Meta's Cloud API directly with approved templates; no BSP lock-in | Accepted (2026-11-19) | D-14 asked to decide at Phase 15 with no default. A thin JSON contract lets the owner pick any Zimbabwean aggregator (or put a small proxy in front of one) without code changes; the Cloud API avoids a BSP fee and keeps template approval in the owner's Meta account. Opt-in per channel, fixed templates, STOP handling, usage metering. Owner still chooses the aggregator vendor |
| ADR-033 | **Production is the shared agribizframework VPS** (66.29.139.201, AlmaLinux 9, https://hr.agribizframework.com), deployed natively with `infrastructure/vps/` beside four other apps; the AWS/Docker design (docs/10 §3, `infrastructure/deployment/`) is kept as the scale-out path, not used now | Accepted (2026-11-20, owner) | Owner decision. Same pattern as the sibling apps (own user, ports, database, systemd units, certbot nginx block). Consequences: no separate staging host - pre-release verification is the nightly CI stack (full Playwright + axe + ZAP baseline on docker compose) plus the local fresh-database end-to-end pass; backups are local nightly dumps (off-server copy pending); monitoring is a systemd timer that emails the platform admin (no CloudWatch/Sentry yet); the CPU has no AVX2, so semantic skill matching is off (D-029); outgoing email through an owner Gmail account (~500/day) |
| ADR-029 | Serve the API with gunicorn **WSGI threaded workers** (`gthread`, 3 x 8 by default) instead of ASGI uvicorn workers, and pool database connections (psycopg pool via Django, `DB_POOL_MAX`=10 per process, `CONN_MAX_AGE`=0) | Accepted (2026-11-18) | P10-T05 load test: under ASGI every synchronous Django view runs on one shared thread per worker (one request at a time), and persistent connections were not reused across requests - one uvicorn worker held 57 PostgreSQL connections after 600 requests, so 4 workers exhausted `max_connections` and the job board returned 500s for 69 % of requests (P95 4.6 s, 117 RPS). The project has no async views or websockets. Pool size: web workers x DB_POOL_MAX + worker processes x DB_POOL_MAX < max_connections (docs/10 §3.1). Revisit ASGI if async views or websockets are introduced |

## Owner decisions (defaults in brackets — development proceeds with defaults)
| ID | Question | Default |
|---|---|---|
| D-01 | Org verification required before publishing? | [Yes — platform admin approves; auto-verify disabled] |
| D-02 | Shortlist dual approval? | [Off by default, configurable per org] |
| D-03 | Retention for unsuccessful applicants | [12 months after vacancy close, then anonymise] |
| D-04 | Duplicate application policy default | [one_active] |
| D-05 | Deadline grace | [0 seconds; server time] |
| D-06 | LLM provider | [None in MVP; adapters for Anthropic/OpenAI behind flag] |
| D-07 | Hosting region | [AWS af-south-1] |
| D-08 | Legal: POTRAZ registration/licensing, DPO, DPA templates | [Counsel review before go-live — go-live gate] |
| D-09 | Production domain | [hr.mudhotech.co.zw (placeholder)] |
| D-10 | Offer voluntary diversity monitoring (P13-T04)? | [No - not built until the owner enables it; see ADR-031] |
| D-10 | Email provider | [AWS SES] |
| D-11 | Pilot employers & roles | [MudhoTech internal + 1 partner; Software Developer role] |
| D-12 | AI acceptance thresholds | [as in docs/09 §5] |
| D-13 | Pricing for plans (USD/ZWG) | [placeholder: Starter $49/mo, Growth $149/mo, Enterprise custom — editable in admin] |
| D-14 | SMS aggregator / WhatsApp BSP | [Default per ADR-032: generic aggregator adapter + Meta Cloud API; owner picks the aggregator vendor] |

## How to add an ADR
Append a row with next id, status, rationale; if it changes the stack or a principle, add a section below with context/options/consequences and update CLAUDE.md §3.

## Phase 01 version verification (P01-T02, 2026-11-08)
Verified against PyPI (`pip index versions`), npm (`npm view`) and nodejs.org/dist/index.json on 2026-11-08.

**ADR-002 note — Django:** latest release is 6.1.x, but the latest **LTS** is still **5.2** (5.2.19; next LTS 6.2 due April 2027).
Decision: stay on Django 5.2 LTS (`django>=5.2.19,<5.3`), Python 3.12 (container image `python:3.12-slim`). Re-evaluate 6.2 LTS in Phase 16.

| Component | Pinned | Notes |
|---|---|---|
| Python | 3.12 | Docker image; local host may have 3.13 (tooling only) |
| Django | 5.2.19 (LTS, `~=5.2.19`) | security support to Apr 2028 |
| djangorestframework | 3.18.x | |
| drf-spectacular | 0.30.x | |
| django-allauth | 65.21.x | headless + mfa extras |
| celery | 5.7.x | redis broker; flower 2.2 |
| psycopg | 3.3.x (binary) | |
| django-environ / django-storages / boto3 | 0.14 / 1.14.6 / 1.43 | |
| cryptography | 50.x | Fernet/MultiFernet |
| nh3 | 0.3.x | HTML sanitiser |
| pytest / pytest-django / factory-boy | 9.2 / 4.14 / 3.3 | |
| ruff / mypy | 0.17 / 2.4 | django-stubs 5.2.x (matches Django 5.2), djangorestframework-stubs 3.16+ |
| uv | 0.13.x | ADR-020 |
| PostgreSQL | 16 (`pgvector/pgvector:pg16`) | matches RDS PostgreSQL 16 target |
| Redis | 7 (`redis:7-alpine`) | |
| Node.js | **24 LTS** (24.22.x, `node:24-alpine`) | Node 26 entered LTS Oct 2026; 24 chosen for ecosystem maturity — re-evaluate Phase 16 |
| Next.js | 16.4.x (App Router) | **ADR-003 note:** latest stable major = 16 |
| React | 19.x | |
| TypeScript | version bundled by create-next-app (5.x/7.x) — `strict: true` | |
| Tailwind CSS | 4.x | shadcn/ui (Tailwind v4 mode) |
| TanStack Query / RHF / Zod | 5.x / 7.x / 4.x | |
| openapi-typescript | 7.x | `npm run gen:api` |
| next-intl | 4.x | |
| Vitest / Playwright / axe-core | 5.x / 1.65 / 4.14 | |

Exact resolved versions are locked in `backend/uv.lock` and `frontend/package-lock.json`.
