# backend/CLAUDE.md — Django backend memory

Loaded automatically when working under `backend/`. Root `CLAUDE.md` rules still apply.

## Layout (as built in Phase 01)
- `config/` settings (`base/dev/test/staging/prod`), `urls.py`, `celery.py`, `asgi.py`, `wsgi.py`
- `apps/core/` — platform utilities (all tested, ≥ 90% coverage):
  - `models.py` `BaseModel`, `TenantModel` + `TenantQuerySet.for_org()/unscoped()` (strict guard raises
    `UnscopedTenantQueryError` when an unscoped tenant queryset is evaluated inside a request),
    `OutboxEvent`, `ProcessedEvent`, `IdempotencyKey`, `FeatureFlag`, `DeadLetter`
  - `outbox.py` `emit()` (inside atomic only), `relay_batch()`, `@idempotent_consumer(name, events=[...])`
  - `idempotency.py` `@idempotent(endpoint="…")` for DRF view methods (`Idempotency-Key` header)
  - `exceptions.py` `DomainError` (+ `ConflictError`, `StaleVersionError`, `InvalidTransitionError`,
    `NotFoundError`, `PermissionDeniedError`, `OrgSuspendedError`, `DeadlinePassedError`) and the envelope handler
  - `middleware.py` `RequestIDMiddleware` · `context.py` contextvars · `logging.py` JSON log context
  - `pagination.py` `StandardPagination` (page) / `StandardCursorPagination` · `viewsets.py` `TenantScopedViewSet`
  - `tasks.py` `BaseTask` (acks_late, 3 retries w/ backoff, DeadLetter on final failure), `ping`, `relay_outbox`
  - `storage.py` `presign_put/presign_get/head_object/move_object/delete_object/put_bytes/get_bytes`
  - `crypto.py` + `fields.py` `EncryptedTextField` (key-id prefixed Fernet, `rotate()`)
  - `flags.py` `is_enabled(key, org=None)` · `health.py` `/healthz` `/readyz` · `time.py` `now()`
  - commands: `send_test_email`, `celery_ping`
- `apps/accounts` (custom `User`, email login) and `apps/organisations` (`Organisation`) — minimal in Phase 01,
  completed in Phase 02.
- `apps/<domain>/` (later phases) — `models.py`, `services.py`, `selectors.py`, `permissions.py`, `tasks.py`,
  `events.py`, `api/{serializers,views,urls,filters}.py`, `admin.py`, `tests/` (+ `tests/factories.py`)
- `ai_engine/` — pure Python (no Django imports; a test enforces it). Django adapters live in `apps/resumes` and
  `apps/screening`. Phase 06 built: `contracts.py` (pydantic, frozen, `extra=forbid`), `extraction/` (guards, pdf,
  docx, sandbox, ocr, quality, sections, dates, skills, parser, pii), `normalisation/` (experience, qualifications,
  titles), `security/injection.py`, `matching/semantic.py`, `tests/benchmark/run_extraction_benchmark.py`.
  Bump `ENGINE_VERSION` when extraction output changes (runs are versioned by it).
- `apps/resumes` — `ExtractionRun`/`DocumentText`/`ExtractedClaim` (encrypted payloads; plain columns only for
  querying), `ClaimCorrection`, candidate-owned `ResumeParse`; `services.py` orchestration (consumers of
  `application.submitted`, `document.accepted`, `document.rejected`; emits `application.evidence_ready`),
  `engine.py` (taxonomy indexes cached per process), `crosscheck.py`, `candidate.py`, `hr.py`.
- `apps/screening` (Phase 07) — `ScreeningRun`/`Evaluation`/`CriterionResult`/`EvaluationEvidence`/
  `HumanVerification` (evaluations are versioned; older ones `superseded`, never edited), `engine.py`
  (builds `EvaluationInput` from claims + verdicts/corrections + answers), `services.evaluate_application`
  (idempotent per input hash; PROCESSING -> UNDER_REVIEW system move), `runs.py` (scopes, chunks of 50),
  `verification.py`, `analytics.py`, `selectors.py` (manual-review band hides all AI output),
  `registry.py` (model registry, synced on `post_migrate`), `quality.py` (daily AI quality counters).
  Screening starts from outbox consumers only when `SCREENING_AUTOSTART` (off in `config.settings.test`).
- Phase 08: `apps/shortlisting` (Shortlist/ShortlistEntry; `services.py` propose/decide/submit/approve/
  return/undo; `selectors.override_stats`); in `apps/applications`: `blind.py` (server-side blind review +
  IdentityReveal), `applicants.py` (applicants query + `ApplicantPagination` cursor with count), `bulk.py`,
  `saved_views.py`, `conflicts.py` (EC-REV-11, EC-ACC-09/10 - applied inside `hr.applications_visible_to`),
  `dashboard.py`, `reconstruct.py` + `reconstruct_pdf.py`; `apps/audit` API (events, CSV export, reconstruct)
  and `audit.log_view()` for every view of candidate data. Hiring managers see shortlisted-onward
  applications unless `JobAssignment.sees_full_pool`.
- `tests/core_testapp/` — test-only models (`Widget` tenant model, `SecretNote` encrypted field); installed
  only by `config.settings.test`.
- `fixtures/` — taxonomy seeds, synthetic CVs (never real data). `schema.yml` — committed OpenAPI schema.

## Rules
1. Tenant models inherit `TenantModel`; query via `Model.objects.for_org(request.organisation)`; views subclass
   `TenantScopedViewSet`. `.unscoped()` only in vetted system code (relays, retention, platform admin).
   Related managers/prefetches reached from an already-loaded tenant object (`job.versions`,
   `version.criteria`) count as scoped; cross-org public reads (job board) use `.unscoped()` + explicit
   status/visibility filters and `Prefetch(..., queryset=X.objects.unscoped())`.
   New org-scoped endpoint ⇒ add an `Endpoint` to `tests/tenancy/registry.py` (RBAC action + success code);
   the cross-tenant suite and the role matrix (`tests/permissions/matrix.py`, derived from
   `apps/organisations/rbac.py`) then cover it automatically. Context-scoped `/hr/...` endpoints set `org_header=True`
   (collection endpoints also `targets_object=False`); give each a `setup` that builds only what it
   needs (`build_ctx(ep)` runs just that setup). Declare permissions explicitly on every view.
2. Writes only through services; services wrap `transaction.atomic()`, lock rows with `select_for_update()` for
   state changes, call `audit.record(...)`, and `outbox.emit(...)` (never `.delay()` inside atomic).
3. Application status changes ONLY via `apps.applications.services.transition()`. Consequential states require
   `actor_type="human"` + reason.
4. Celery tasks: `@shared_task(base=BaseTask)`; consumers via `@idempotent_consumer`; check current status at
   start (withdrawn → no-op). Task routes by module prefix are in `CELERY_TASK_ROUTES`.
5. Serializers: explicit `fields`, reject unknown input, never accept `organisation`, `status`, `score`, `role`
   from clients unless the endpoint is the dedicated action for it.
6. Errors: raise `DomainError(code, message, status_code, details)`; the handler renders the envelope.
7. Use `apps.core.time.now()` (server authoritative). Timezone-aware everything.
8. Sensitive text fields use `EncryptedTextField`. No PII in logs.
9. OpenAPI: annotate with `@extend_schema`; after API changes run
   `python manage.py spectacular --file schema.yml --validate --fail-on-warn` and commit; then `npm run gen:api`.
10. Migrations: backward compatible; data migrations idempotent; run `makemigrations --check` before committing.
11. User-facing messages go through `apps.notifications.delivery.notify(user, key, context, dedupe_key=...)`
    inside the business transaction (never `queue_email` for candidate/staff notifications; that is for
    auth/security mail). New kinds: add to `notifications/registry.py` + `defaults.py` (no scores/reasons).
12. Seed data that tests rely on (templates, decision reasons) is (re)created on `post_migrate`, because
    transactional tests flush the DB; a data migration alone is not enough.
13. Migrations that use pgvector/trigram/unaccent depend on `core.0002_postgres_extensions` (fresh CI DBs).
14. Untrusted files are parsed via `ai_engine.extraction.sandbox.run_extraction` (subprocess + limits) unless
    `EXTRACTION_SANDBOX=False` (tests). Extraction starts from outbox consumers only when `RESUMES_AUTOSTART`
    (off in `config.settings.test`; resumes tests switch it on in their conftest).
15. Embeddings: the `ml` extra (sentence-transformers, CPU torch) exists only in the worker image (ADR-025);
    tests use `EMBEDDING_MODEL="hashing-384"`. After `load_taxonomy`, run `embed_skills` in a worker.

## Commands
Inside the container (`docker compose exec backend …`):
```
python manage.py migrate | makemigrations --check --dry-run | send_test_email | celery_ping
pytest -q  |  pytest apps/<app> -q  |  pytest -m "not slow"  |  pytest --cov=apps --cov=ai_engine
ruff format . && ruff check . && mypy apps ai_engine
celery -A config worker -Q documents -c 2 -l info
python manage.py load_taxonomy && python manage.py embed_skills          # worker container (model)
python -m ai_engine.tests.benchmark.run_extraction_benchmark --workers 2 --semantic --check  # worker image
python -m ai_engine.tests.benchmark.run_screening_benchmark --out-dir ../docs/reports --check  # P07 targets
python manage.py check_human_decisions        # 0 consequential transitions without a human (exit 1 otherwise)
DEMO_PASSWORD=... python manage.py seed_core_scenario --count 100 --delay-minutes 1   # after seed_demo (e2e)
```
In Git Bash, prefix docker commands that pass container paths with `MSYS_NO_PATHCONV=1`.
On the host (Windows, `backend/`): `python -m uv sync` creates `.venv` (Python 3.12), then
`.venv/Scripts/python -m pytest -q` — host runs use `localhost:15432` (Postgres) and `localhost:6380` (Redis)
from the dev stack; `.env` is NOT auto-loaded (set `DJANGO_READ_DOT_ENV=true` to opt in).
pytest always uses `config.settings.test` (`--ds` in `pyproject.toml`), even inside containers.
