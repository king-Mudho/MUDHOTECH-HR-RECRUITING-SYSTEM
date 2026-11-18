# Runbook — processing backlog and dead letters

P11-T08. Alarms: `mhrs-<env>-documents-queue` (> 500), `-processing-backlog` (oldest unfinished application
> 15 min), `-outbox-lag` (> 5 min), `-dead-letters` (> 10, EC-OPS-07), `-ops-metrics-missing`.
Code: `apps/core/ops_metrics.py`, `apps/core/deadletters.py`, `apps/resumes/recovery.py`.

`DC="docker compose -f /opt/mhrs/docker-compose.prod.yml --env-file /opt/mhrs/.env"` in every command below.

## Symptoms
- Applications stay in *Submitted* / *Processing*; HR sees "being prepared" for a long time.
- Queue depth climbing (Flower → Queues, or the `QueueDepth` metric); dead letters accumulating.

## Impact
Submissions are **never lost** (they are committed before any background work, docs/02); only screening,
extraction and notifications are delayed. Candidates see their submission confirmed regardless.

## Immediate actions
1. Are the workers alive? `$DC ps` (all `healthy`?) and
   `$DC exec backend python manage.py celery_ping` (every worker answers `pong`).
2. Is the broker healthy? `$DC exec redis redis-cli info memory | grep used_memory_human` (limit 384 MB,
   `noeviction`: if full, writes fail — see Diagnosis).
3. Is beat running (it relays the outbox every 2 s)? `$DC logs --since 5m beat | tail`.

## Diagnosis
| Finding | Cause | Fix |
|---|---|---|
| A worker container unhealthy / restarting | OOM (large CV, OCR) or crash loop | `$DC logs --tail 200 worker-documents`; `docker inspect -f '{{.State.OOMKilled}}' <id>`; restart: `$DC up -d --no-deps worker-documents` |
| `documents` queue deep, workers busy | a burst (viral vacancy, EC-OPS-10) | scale temporarily: `$DC up -d --no-deps --scale worker-documents=2 worker-documents` (watch memory: 1.5 GB each) |
| Outbox lag growing, queues empty | beat down or relay failing | `$DC up -d --no-deps beat`; `$DC logs beat`; outbox rows: `/django-admin/core/outboxevent/?status__exact=pending` |
| Applications stuck in *Processing* > 15 min with empty queues | a task was lost (worker killed mid-task) | the beat job `recover_stuck_processing` re-queues them every 5 min (D-012); force now: `$DC exec backend celery -A config call apps.resumes.tasks.recover_stuck_processing` |
| Dead letters | a task failed all retries (bug, bad input, external outage) | see below |
| Redis memory full | backlog too large or a leak | scale workers first; never `FLUSHALL` (it deletes queued tasks); add memory or move to ElastiCache |

## Resolution — dead letters (EC-OPS-07)
1. Open `/django-admin/core/deadletter/?state=open` (operator IP allow-list). Group by task name; read `error`
   and `traceback` (no personal data is stored in them — check before pasting anywhere).
2. **External outage over** (S3, SES, clamd were down): select them → *Retry selected tasks*. Every task is
   idempotent, so retrying an already-done task is harmless.
3. **Object gone** (application withdrawn, document erased): *Mark selected as resolved without retrying*.
4. **A bug**: fix and deploy first, then retry. Both actions are audited (`dead_letter.retried` / `.resolved`).

## Verification
`DeadLettersOpen` back under 10, `ProcessingBacklogAgeSeconds` under 900, queue depths falling in CloudWatch;
the alarms return to OK (an OK notification is emailed).

## Follow-up
Incident record if candidates or HR were affected for > 1 hour. Scale-ups by `--scale` are lost on the next
deploy: make a lasting change in `docker-compose.prod.yml` (concurrency `-c`, memory limit) via a PR.
