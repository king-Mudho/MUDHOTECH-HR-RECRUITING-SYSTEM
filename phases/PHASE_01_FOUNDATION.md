# PHASE 01 — Foundation & Development Environment

**Release:** MVP · **Modules:** platform foundation · **Depends on:** nothing
**Read first:** `CLAUDE.md`, `docs/02_ARCHITECTURE.md`, `docs/10_DEPLOYMENT_OPERATIONS.md §1–2`, `docs/11_DECISIONS_LOG.md`

## Goal
A secure, running skeleton: monorepo, Dockerised dev stack, Django + DRF + Celery + Postgres + Redis + MinIO +
Mailpit + ClamAV, Next.js app shell, CI, core platform utilities (BaseModel, outbox, idempotency, error envelope,
request IDs, health checks). Everything later phases build on.

## Tasks
- [x] **P01-T01** — Initialise git repo (if not already), `.gitignore` (Python, Node, env, media, .DS_Store, `*.docx~`), `.gitattributes` (LF; `*.ps1` CRLF), `.editorconfig`, `README.md` quick start, `CHANGELOG.md`, `LICENSE` (proprietary — MudhoTech Solutions (Pvt) Ltd). Move nothing else; keep the blueprint `.docx` at root (or `docs/source/`).
- [x] **P01-T02** — Verify current stable versions (Django LTS, DRF, Celery, Next.js, Node LTS, PostgreSQL, pgvector image) via official docs/PyPI/npm; record chosen versions in `docs/11_DECISIONS_LOG.md` (ADR-002/003 notes) and pin them.
- [x] **P01-T03** — Backend scaffold: `backend/pyproject.toml` (uv), `config/` with split settings (`base/dev/test/staging/prod`), django-environ, `config/celery.py`, `config/urls.py` with `/api/v1/` router, `/api/docs/` (Swagger) + `/api/schema/` (drf-spectacular), `apps/` package, `ai_engine/` package placeholder with `contracts.py`.
- [x] **P01-T04** — `apps.core`: `BaseModel` (UUID pk, timestamps), `TenantModel` + `TenantQuerySet.for_org()` + strict unscoped guard (raises in dev/test when evaluated without scoping in request context), `RequestIDMiddleware` (`X-Request-ID` in/out, contextvar for logs), JSON structured logging config, standard **error envelope** exception handler (all DRF + Django errors mapped; codes per `docs/04 §1`), pagination classes (page + cursor), base `TenantScopedViewSet`.
- [x] **P01-T05** — `apps.core.outbox`: `OutboxEvent`, `ProcessedEvent` models, `emit(event_type, aggregate, payload, dedupe_key)` (must be called inside atomic), relay task (`SELECT … FOR UPDATE SKIP LOCKED`, batch 100), `on_commit` kick, consumer decorator `@idempotent_consumer("name")`. Tests: event not published if transaction rolls back; dedupe; relay concurrency (two relays don't double publish).
- [x] **P01-T06** — `apps.core.idempotency`: `IdempotencyKey` model + DRF mixin/decorator `@idempotent(endpoint="…")` storing response; same key+same body → replay; same key+different body → 422 `idempotency_key_reuse`. Tests.
- [x] **P01-T07** — Health endpoints `/healthz` and `/readyz` (DB, Redis, S3 checks with timeouts). Feature flag model + `is_enabled(key, org=None)` helper with cache. DeadLetter model + Celery base task class (`acks_late`, retries w/ backoff, writes DeadLetter on final failure, logs with request/task ids).
- [x] **P01-T08** — Storage service `apps.core.storage` (django-storages/boto3): buckets per purpose, `presign_put`, `presign_get(ttl=60)`, `move_object`, `delete_object`, `head_object`. MinIO in dev with `minio-init` creating buckets: `mhrs-uploads-quarantine`, `mhrs-documents`, `mhrs-exports`, `mhrs-public`.
- [x] **P01-T09** — Field encryption utility (`EncryptedTextField` using Fernet MultiFernet with key ids from `FIELD_ENCRYPTION_KEYS`); tests for rotate/read old.
- [ ] **P01-T10** — Docker: `backend/Dockerfile` (python:3.12-slim, non-root user, uv install), `backend/Dockerfile.worker` (adds tesseract-ocr, poppler-utils, libmagic), `frontend/Dockerfile` (node LTS, multi-stage). `docker-compose.yml` (**`name: mhrs`**) with services per `docs/10 §1` incl. healthchecks; `docker-compose.prod.yml` skeleton; `.env.example` complete per `docs/10 §2`.
- [ ] **P01-T11** — Frontend scaffold: create Next.js app (TypeScript, App Router, Tailwind, ESLint, `src/` dir) **in a temp folder and move files into `frontend/`** (create-next-app refuses non-empty dirs because `frontend/CLAUDE.md` exists). Add shadcn/ui init, Prettier, Vitest + Testing Library, Playwright, TanStack Query provider, `next-intl` with `messages/en.json`, Inter font, theme tokens from `docs/08 §1`, route groups `(public)`, `(candidate)`, `(hr)`, `(admin)` with placeholder layouts, `next.config` rewrites `/api/:path* → ${API_INTERNAL_URL}/api/:path*`.
- [ ] **P01-T12** — API client: `src/lib/api-client.ts` (fetch wrapper with credentials, CSRF header from cookie, error envelope parsing → typed `ApiError`, request id surfaced), `npm run gen:api` script (openapi-typescript from backend schema → `src/types/api.d.ts`).
- [ ] **P01-T13** — Base UI shell: public header/footer with "MUDHOTECH HR RECRUITING SYSTEM" branding, HR shell (sidebar nav, top bar placeholder org switcher & notifications bell), candidate shell, admin shell; `EmptyState`, `ErrorState`, `Skeleton`, `StatusBadge` primitives; 404/500 pages.
- [ ] **P01-T14** — Tooling: backend `ruff` + `mypy` (django-stubs, drf-stubs) + `pytest` config + `factory_boy`; pre-commit config (ruff, prettier, eslint, end-of-file, detect-secrets). `scripts/dev-up.ps1`, `scripts/dev-up.sh`, `scripts/ec_coverage.py` (scans tests for EC ids listed in phases marked done).
- [ ] **P01-T15** — CI `.github/workflows/ci.yml` per `docs/09 §6` (backend lint/type/test with Postgres+Redis services; frontend lint/typecheck/test/build; schema drift check). Nightly workflow skeleton.
- [ ] **P01-T16** — Write nested memories: confirm `backend/CLAUDE.md` and `frontend/CLAUDE.md` are accurate for the scaffold produced (update commands/paths); add `docs/runbooks/README.md`.
- [ ] **P01-T17** — Smoke test: `docker compose up -d --build` from clean clone works on Windows; `/readyz` 200; frontend renders home page via proxy; Celery worker processes a `ping` task; Mailpit receives a test email via management command `send_test_email`.

## Edge cases covered in this phase
EC-OPS-01 (outbox survives Redis down — test with broker unavailable), EC-OPS-06 (server time authority helper `core.time.now()`).

## Exit criteria
- [ ] Fresh clone → `scripts/dev-up.ps1` → full stack healthy in < 10 min.
- [ ] CI green on main.
- [ ] Error envelope, request id, outbox, idempotency, storage, encryption utilities tested (≥ 90% coverage of `apps/core`).
- [ ] OpenAPI available at `/api/docs/`; `npm run gen:api` produces types; `tsc --noEmit` passes.
- [ ] PROGRESS.md updated; phase closed.

## Verification
```bash
docker compose up -d --build && docker compose ps
curl -fsS http://localhost:8000/readyz
docker compose exec backend pytest -q && docker compose exec backend ruff check . && docker compose exec backend mypy apps ai_engine
cd frontend && npm run lint && npm run typecheck && npm run test && npm run build
```
