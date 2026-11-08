# backend/CLAUDE.md — Django backend memory

Loaded automatically when working under `backend/`. Root `CLAUDE.md` rules still apply.

## Layout
- `config/` settings (`base/dev/test/staging/prod`), `urls.py`, `celery.py`, `asgi.py`
- `apps/<domain>/` — `models.py`, `services.py` (write logic, transactions, audit, outbox), `selectors.py` (reads, always tenant-scoped), `permissions.py`, `tasks.py`, `events.py` (outbox event names/payload builders), `api/{serializers,views,urls,filters}.py`, `admin.py`, `tests/`
- `ai_engine/` — pure Python (no Django imports). Django adapters live in `apps/resumes` and `apps/screening`.
- `fixtures/` — taxonomy seeds, synthetic CVs (never real data).

## Rules
1. Tenant models inherit `TenantModel`; query via `Model.objects.for_org(request.organisation)`; views subclass `TenantScopedViewSet`. New endpoint ⇒ register in `tests/tenancy/registry.py` and `tests/permissions/matrix.py`.
2. Writes only through services; services wrap `transaction.atomic()`, lock rows with `select_for_update()` for state changes, call `audit.record(...)`, and `outbox.emit(...)` (never `.delay()` inside atomic).
3. Application status changes ONLY via `apps.applications.services.transition()`. Consequential states require `actor_type="human"` + reason.
4. Celery tasks: inherit `apps.core.tasks.BaseTask` (acks_late, retries, dead letters); decorate consumers with `@idempotent_consumer`; check current status at start (withdrawn → no-op).
5. Serializers: explicit `fields`, reject unknown input, never accept `organisation`, `status`, `score`, `role` from clients unless the endpoint is the dedicated action for it.
6. Errors: raise `apps.core.exceptions.DomainError(code, message, status)`; the handler renders the envelope.
7. Use `apps.core.time.now()` (server authoritative). Timezone-aware everything.
8. Sensitive text fields use `EncryptedTextField`. No PII in logs.
9. OpenAPI: annotate with `@extend_schema`; after API changes run `python manage.py spectacular --file schema.yml` and commit.
10. Migrations: backward compatible; data migrations idempotent; run `makemigrations --check` before committing.

## Commands (inside container)
```
python manage.py migrate | makemigrations --check --dry-run | seed_demo | load_taxonomy | run_pilot_benchmark
pytest -q  |  pytest apps/<app> -q  |  pytest -m "not slow"  |  pytest --cov=apps --cov=ai_engine
ruff format . && ruff check . && mypy apps ai_engine
celery -A config worker -Q documents -c 2 -l info
```
