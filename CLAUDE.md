# CLAUDE.md — MUDHOTECH HR RECRUITING SYSTEM (Project Memory)

> This file is the **primary memory** for any Claude Code agent working in this repository.
> Read it fully at the start of every session, then read `PROGRESS.md`, then the current phase file in `phases/`.

---

## 1. What we are building

**MUDHOTECH HR RECRUITING SYSTEM** (short: **MHRS**) — a secure, multi-tenant, web-based
Applicant Tracking System (ATS) with an **explainable, human-controlled AI screening engine**.

- Owner / vendor: **MudhoTech Solutions (Pvt) Ltd**, Harare, Zimbabwe.
- Organisations (tenants) advertise vacancies, collect applications + CVs + job-specific
  questionnaire answers, get **evidence-based, explainable** AI assessments, and HR staff
  **approve** shortlists, run interviews, make offers and record hires.
- Core scenario (the MVP must demonstrate this end to end): an employer publishes a
  *Software Developer* vacancy → 100 candidates apply with CVs and answers → workers parse and
  evaluate every application against a **versioned, HR-approved rubric** → HR inspects evidence,
  clarifies uncertain cases and **approves** a shortlist → shortlisted candidates are notified.

The name is **MUDHOTECH HR RECRUITING SYSTEM**. Never use "Programac" or "TalentMatch AI" anywhere
(code, UI, docs, package names). Package/slug prefix: `mhrs`.

## 2. Non-negotiable principles (apply to every line of code)

1. **Human-in-control** — AI only *recommends*. No consequential state (`shortlisted`, `not_selected`,
   `offer`, `hired`) is ever set without an authenticated human actor + reason recorded.
2. **Evidence-first** — every extracted claim / criterion result links to a source (document, page,
   snippet, question response) or is explicitly labelled `missing` / `inferred` / `conflicting`.
3. **Missing ≠ negative** — absence of a keyword or data is *unknown*, never an automatic fail.
4. **Tenant isolation** — every tenant-owned query is scoped by `organisation_id` server-side, with
   object-level permission checks. Cross-tenant access tests are mandatory for every new endpoint.
5. **Versioned decisions** — rubrics, job versions, evaluations, prompts and model versions are
   immutable once used; re-evaluation creates a new version, never overwrites.
6. **Submission resilience** — an application, once submitted, is never lost because AI, storage
   scanning, email or Redis failed later. Use DB transactions + transactional outbox.
7. **Candidate dignity & fairness** — never infer or score protected attributes (race, ethnicity,
   tribe, religion, gender, age, marital status, pregnancy, disability, political opinion, HIV status,
   photo/appearance). Never penalise career gaps or formatting by default.
8. **Security by default** — CV text is *untrusted input* (prompt-injection, malware, XSS).
9. **Data minimisation & privacy** — Zimbabwe Cyber and Data Protection Act [Ch. 12:07] + SI 155 of 2024.

## 3. Confirmed technology stack (do not change without an ADR in `docs/11_DECISIONS_LOG.md`)

| Layer | Choice |
|---|---|
| Frontend | Next.js (App Router, latest stable — verify at Phase 1), React, **TypeScript strict**, Tailwind CSS, shadcn/ui, TanStack Query, React Hook Form + Zod, `openapi-typescript` generated API types |
| Backend | Python 3.12, **Django 5.2 LTS** (unless a newer LTS exists at Phase 1 — record ADR), Django REST Framework, drf-spectacular, django-allauth (headless + MFA), django-filter, django-storages |
| DB | PostgreSQL 16+ with `pgvector` and `pg_trgm`; full-text search via PostgreSQL |
| Async | Celery + Redis (queues: `default`, `documents`, `ai`, `notifications`, `reports`), Celery Beat |
| AI/NLP | spaCy, rule engine + skills taxonomy, sentence-transformers embeddings (local), optional LLM via provider adapter (disabled by default) |
| Docs | PyMuPDF (primary), pdfplumber (fallback), python-docx, Tesseract OCR (fallback), ClamAV |
| Storage | Private S3-compatible (SeaweedFS S3 gateway in dev (ADR-021), AWS S3 in prod), presigned URLs |
| Email | Mailpit (dev), AWS SES / SMTP (prod) via outbox |
| Infra | Docker Compose, Nginx, AWS EC2 Ubuntu 24.04, GitHub Actions, Sentry, structured JSON logs |
| Tests | pytest + pytest-django + factory_boy, Vitest + Testing Library, Playwright + axe-core, Locust |

## 4. Repository layout (target)

```
MUDHOTECH HR RECRUITING SYSTEM/          ← repo root (NOTE: path has spaces — always quote paths)
├── CLAUDE.md            ← this file (project memory)
├── PROGRESS.md          ← single source of truth for progress — UPDATE EVERY SESSION
├── README.md
├── AGENT_START_PROMPT.md← prompt the owner pastes to start/resume the agent
├── .claude/commands/    ← slash commands: /status /next-task /verify-phase /close-phase
├── docs/                ← finalized specs (01_SRS … 12_GLOSSARY)
├── phases/              ← PHASE_01 … PHASE_16 implementation plans with task checklists
├── backend/             ← Django project (config/, apps/, ai_engine/, tests/)  + backend/CLAUDE.md
├── frontend/            ← Next.js app                                           + frontend/CLAUDE.md
├── infrastructure/      ← docker/, nginx/, deployment/, monitoring/
├── scripts/             ← helper scripts (PowerShell + bash)
├── docker-compose.yml   ← `name: mhrs` set explicitly (path contains spaces)
└── .env.example
```

## 5. How to work (agent operating loop)

Every session:

1. Read `CLAUDE.md` (this) → `PROGRESS.md` → the **current phase file** named in PROGRESS.md.
2. Pick the **first unchecked task** of the current phase (tasks are ordered; respect dependencies).
3. Before coding, read the relevant spec sections referenced by the task (`docs/...`).
4. Implement the task **fully** per the Definition of Done (§7). Small, coherent commits.
5. Run the verification commands for the task (tests, lint, type-check, migrations check).
6. Tick the task in the phase file **and** in `PROGRESS.md`; append a line to the PROGRESS session log
   (date, task IDs, what changed, follow-ups).
7. When all tasks of a phase are ticked, run the phase **Exit Criteria** checklist. Only when every exit
   criterion passes: mark the phase ✅ in PROGRESS.md, set the next phase as current, commit with
   message `chore(progress): close phase NN`.
8. Continue to the next task / phase without waiting for permission unless a **STOP condition** occurs.

### STOP conditions (pause and ask the owner)
- A decision marked `OWNER-DECISION` in `docs/11_DECISIONS_LOG.md` is needed and has no default.
- Real credentials/secrets/production access are required (AWS keys, SES, Paynow keys, domain DNS).
- A change would break a non-negotiable principle (§2) or alter the confirmed stack (§3).
- Destructive operations on data outside the dev environment.
- Tests cannot be made to pass after 3 genuinely different approaches — record blocker in PROGRESS.md.

Otherwise: **choose the documented default and continue** (the owner prefers minimal back-and-forth).

## 6. Coding conventions

### Backend (Django)
- Apps live in `backend/apps/<name>/` with `models.py`, `services.py` (business logic), `selectors.py`
  (read queries), `api/serializers.py`, `api/views.py`, `api/urls.py`, `permissions.py`, `tasks.py`,
  `events.py`, `admin.py`, `tests/`. **Views stay thin; logic lives in services.**
- All models inherit `apps.core.models.BaseModel` (UUID `id`, `created_at`, `updated_at`) and tenant
  models inherit `TenantModel` (adds `organisation` FK + `TenantManager` requiring scoping).
- State changes go through `apps.<x>.services.transition_*()` functions which validate the state
  machine, write a status event + audit event inside `transaction.atomic()`.
- Async side effects are emitted via the **outbox** (`apps.core.outbox.emit(event, payload)`) inside the
  same transaction — never call `.delay()` directly inside a transaction body.
- Celery tasks are **idempotent** (idempotency key = `<event>:<object_id>:<version>`), use `acks_late`,
  bounded retries with exponential backoff, and a dead-letter record on final failure.
- API: `/api/v1/…`, DRF, cursor or page-number pagination, standard error envelope
  `{ "error": { "code", "message", "details", "request_id" } }`, OpenAPI via drf-spectacular.
- Settings split: `config/settings/{base,dev,test,staging,prod}.py`, all secrets from env (django-environ).
- Formatting/lint: `ruff format`, `ruff check`, `mypy` (django-stubs) on `apps/` and `ai_engine/`.
- Time: store UTC (`USE_TZ=True`); default display TZ `Africa/Harare`; vacancies carry their own TZ.
- Money: `Decimal` + ISO currency (`USD`, `ZWG`); never float.
- Phone: E.164 via `phonenumbers`, default region `ZW`.

### Frontend (Next.js)
- `frontend/src/app` (routes, route groups `(public)`, `(candidate)`, `(hr)`, `(admin)`),
  `src/features/<domain>` (components, hooks, api, schemas), `src/components/ui` (shadcn),
  `src/lib` (api client, auth, utils), `src/types/api.d.ts` (generated — never hand-edit).
- Server Components by default; Client Components only for interactivity.
- Same-origin API via Next.js rewrites `/api/* → backend` so session + CSRF cookies work.
- Every form: React Hook Form + Zod; server errors mapped to fields; accessible labels; no `any`.
- Lint/format: ESLint + Prettier; `tsc --noEmit` must pass.

### Git
- Conventional commits: `feat(jobs): …`, `fix(screening): …`, `test(…)`, `docs(…)`, `chore(…)`.
- Branch per phase optional: `phase/NN-short-name`; merge to `main` when the phase closes.
- Never commit `.env`, secrets, real CVs, or personal data. Test CVs are synthetic only.

## 7. Definition of Done (per task / user story)
A task is done only when ALL apply (skip items that are clearly not applicable):
- [ ] Models + migrations (`makemigrations --check` clean), admin registration where useful
- [ ] Services + selectors with type hints; serializers/views with explicit permissions
- [ ] Tenant scoping + object-level permission + **cross-tenant negative test**
- [ ] Audit events for sensitive actions
- [ ] Unit + API tests (happy path, validation errors, permission denials, edge cases listed in phase)
- [ ] OpenAPI schema updated; frontend types regenerated (`npm run gen:api`)
- [ ] Frontend page/components with loading, empty, error states; mobile-first; keyboard + labels
- [ ] Lint, type-check and full test suite pass
- [ ] PROGRESS.md + phase file updated

## 8. Common commands (run from repo root; work in PowerShell, Git Bash or WSL)

```bash
docker compose up -d --build                     # start full dev stack
docker compose exec backend python manage.py migrate
docker compose exec backend python manage.py makemigrations --check --dry-run
docker compose exec backend pytest -q
docker compose exec backend ruff check . && docker compose exec backend mypy apps ai_engine
docker compose exec backend python manage.py spectacular --file /app/schema.yml
cd frontend && npm run lint && npm run typecheck && npm run test && npm run gen:api
npx playwright test                              # from frontend/
docker compose logs -f worker                    # celery worker logs
```

Dev URLs: frontend http://localhost:3000 · API http://localhost:8000/api/v1/ · API docs /api/docs/ ·
Mailpit http://localhost:8025 · S3 (SeaweedFS) http://localhost:9000, filer UI http://localhost:8888 · Flower http://localhost:5555

## 9. Key documents (read the relevant one before each task)

| Doc | Content |
|---|---|
| `docs/01_SRS.md` | Final requirements: scope, roles, 24 modules, FR/NFR IDs, acceptance criteria |
| `docs/02_ARCHITECTURE.md` | Architecture, stack, folder layout, request/event flows |
| `docs/03_DATABASE_SCHEMA.md` | Every model, field, constraint, index |
| `docs/04_API_CONTRACT.md` | Endpoints, permissions, error envelope, pagination, idempotency |
| `docs/05_AI_ENGINE.md` | Extraction → normalisation → matching → scoring → explanation; LLM guardrails |
| `docs/06_SECURITY_PRIVACY_COMPLIANCE.md` | Security baseline, CDPA/SI 155 controls, retention |
| `docs/07_EDGE_CASES.md` | 150+ edge cases with required behaviour (EC-IDs referenced from phases) |
| `docs/08_UI_UX_SPEC.md` | Routes, screens, components, design system, accessibility |
| `docs/09_TESTING_STRATEGY.md` | Test pyramid, fixtures, synthetic CV set, AI validation, load tests |
| `docs/10_DEPLOYMENT_OPERATIONS.md` | Environments, AWS EC2, Nginx, backups, monitoring, runbooks |
| `docs/11_DECISIONS_LOG.md` | ADRs + defaults chosen + open owner decisions |
| `docs/12_GLOSSARY.md` | Domain terms |
| `MUDHOTECH_HR_RECRUITING_SYSTEM_Complete_Project_Blueprint.docx` | Original blueprint (source) |

## 10. Things that commonly go wrong (read before coding)
- Forgetting tenant scoping in a new selector → always use `Model.objects.for_org(org)`; tests catch it.
- Calling Celery inside `atomic()` → task runs before commit; use outbox / `transaction.on_commit`.
- Trusting client-supplied `organisation_id`, `role`, `status` or `score` → derive server-side.
- Rendering job descriptions as raw HTML → sanitise with `nh3` server-side; render safely client-side.
- Exporting CSV/XLSX with user text → neutralise formula injection (`=`,`+`,`-`,`@`, tab, CR).
- Sending CV text to an LLM unredacted or obeying instructions inside a CV → see `docs/05_AI_ENGINE.md §9`.
- `create-next-app` refuses non-empty folders → scaffold into a temp dir and move files in (Phase 1).
- Docker Compose project name from a path with spaces → `name: mhrs` is set at the top of compose.
