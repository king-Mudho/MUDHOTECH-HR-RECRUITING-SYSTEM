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
| ADR-012 | PostgreSQL RLS as Phase 9 hardening (evaluate; implement if overhead acceptable) | Accepted (evaluate) | Second line of tenant defence |
| ADR-013 | Blind review mode default ON for first-pass screening | Accepted | Bias reduction |
| ADR-014 | Notification delay/undo window default 15 min after shortlist approval | Accepted | Mistake recovery |
| ADR-015 | Billing via Paynow (EcoCash, OneMoney, cards) first; Stripe optional later | Accepted | Zimbabwe market |
| ADR-016 | Hosting AWS, EC2 Ubuntu + Docker Compose for pilot; RDS PostgreSQL | Accepted | Owner's existing practice |
| ADR-017 | English-only parsing in MVP; i18n-ready UI | Accepted | Scope |
| ADR-018 | Hash-chained append-only audit table | Accepted | Tamper evidence |
| ADR-019 | Interview panelists don't see AI scores by default | Accepted | Anchoring bias |
| ADR-020 | Package manager: `uv` for Python (pyproject), npm for frontend | Accepted | Speed, lockfiles |
| ADR-021 | Dev-only S3 emulator: **SeaweedFS** (`chrislusf/seaweedfs`, S3 gateway on :9000) + `amazon/aws-cli` bucket init, replacing MinIO in dev | Accepted (2026-11-08) | `minio/minio` and `minio/mc` images are no longer publicly pullable (Docker Hub/quay deny). Production remains AWS S3; app code uses plain boto3/S3 API so the emulator is swappable (RustFS is the fallback). |
| ADR-022 | Dev host ports are configurable via `*_HOST_PORT` env vars; defaults Postgres **55432**, Redis **6380** (others standard) | Accepted (2026-11-08) | Avoid clashes with other local Postgres/Redis instances on developer machines; container-internal ports unchanged |

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
| D-10 | Email provider | [AWS SES] |
| D-11 | Pilot employers & roles | [MudhoTech internal + 1 partner; Software Developer role] |
| D-12 | AI acceptance thresholds | [as in docs/09 §5] |
| D-13 | Pricing for plans (USD/ZWG) | [placeholder: Starter $49/mo, Growth $149/mo, Enterprise custom — editable in admin] |
| D-14 | SMS aggregator / WhatsApp BSP | [decide at Phase 15] |

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
