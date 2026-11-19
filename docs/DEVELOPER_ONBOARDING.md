# Developer onboarding

Welcome to the MUDHOTECH HR RECRUITING SYSTEM (MHRS). This page gets you from a fresh clone to a
first change; `CLAUDE.md`, `backend/CLAUDE.md` and `frontend/CLAUDE.md` hold the detailed rules.

## 1. Read first (an hour)

1. `CLAUDE.md` – the non-negotiable principles (human-in-control, evidence-first, missing ≠
   negative, tenant isolation, versioned decisions, submission resilience, candidate dignity,
   security, privacy). Every change is reviewed against them.
2. `docs/02_ARCHITECTURE.md` (components, flows, diagrams) and `docs/architecture/ERD.md`.
3. `docs/11_DECISIONS_LOG.md` – why things are the way they are (ADRs) and open owner decisions.

## 2. Run it

Requirements: Docker Desktop (8 GB RAM recommended), Node 22+, Python 3.12 with `uv`.

```
cp .env.example .env              # dev defaults; never commit .env
docker compose up -d --build      # postgres, redis, s3, mailpit, backend, workers, frontend
docker compose exec backend python manage.py migrate
DEMO_PASSWORD=... docker compose exec backend python manage.py seed_demo
```

Frontend http://localhost:3000 · API http://localhost:8000/api/v1/ · API docs /api/docs/ ·
Mailpit http://localhost:8025. Demo accounts are listed by `seed_demo`.

Low-memory machines: run only Postgres/Redis in Docker and the backend on the host
(`cd backend && python -m uv sync && .venv/Scripts/python -m pytest -q`), see `backend/CLAUDE.md`.

## 3. How code is organised

- Backend: `backend/apps/<domain>/` with `models.py`, `services.py` (all writes, in transactions),
  `selectors.py` (reads), `api/`, `tasks.py`, `tests/`. Views stay thin.
- Tenant data: inherit `TenantModel`, query with `Model.objects.for_org(org)`; PostgreSQL row-level
  security is the second line of defence. New staff endpoints are registered in
  `backend/tests/tenancy/` so the cross-tenant suite and permission matrix cover them automatically.
- Side effects (email, AI, webhooks, integrations) go through the transactional outbox
  (`apps.core.outbox.emit`) and idempotent consumers – never `.delay()` inside a transaction.
- Application status changes only through `apps.applications.services.transition()`; consequential
  outcomes need a human actor and a reason.
- Frontend: `frontend/src/app` routes, `src/features/<domain>` components and hooks; all text in
  `frontend/messages/en.json`; API types generated from `backend/schema.yml` (`npm run gen:api`).

## 4. Making a change

1. Pick the task, read the referenced docs and edge cases (`docs/07_EDGE_CASES.md`).
2. Write the service + tests first (happy path, validation, permissions, cross-tenant).
3. Backend checks: `ruff format . && ruff check . && mypy apps ai_engine && pytest -q`;
   `python manage.py makemigrations --check --dry-run`; after API changes
   `python manage.py spectacular --file schema.yml --validate --fail-on-warn`.
4. Frontend checks: `npm run gen:api && npm run lint && npm run typecheck && npm run test`.
5. Conventional commit (`feat(jobs): …`), push, and check CI (and the nightly) for your commit.

## 5. Where to look when something breaks

- Logs are JSON with a `request_id`; error responses show the same id to users.
- Background failures land in dead letters (platform admin → Dead letters; retry/resolve).
- Runbooks: `docs/runbooks/`. Health: `/healthz`, `/readyz`, platform admin → System health.
- Integrations run in sandbox mode unless `INTEGRATIONS_SANDBOX=false` (see `docs/integrations/`).
