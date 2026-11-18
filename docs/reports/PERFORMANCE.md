# Performance — P10-T05 load tests and P10-T06 throughput

Targets (docs/01 NFR-PERF): **P95 API latency < 400 ms** for list/detail endpoints at pilot load
(excluding file transfer); 100 CVs end-to-end ≤ 15 min on 2 worker processes; public job pages
LCP < 2.5 s on simulated 3G.

## 1. Server-side measurements (2026-11-17, host: Django + PostgreSQL 16 in Docker, Windows)

### 1.1 HR applicants list with 5,000 applications

`backend/tests/integration/test_applicants_scale.py` (marked `slow`; asserts P95 < 400 ms), 30
requests per view after a warm-up, in-process (no network/proxy):

| View | P95 |
|---|---|
| Default (score, descending) | 146 ms |
| Band filter | 94 ms |
| Essentials unknown + tag | 175 ms |
| Oldest first | 264 ms |
| Search | 92 ms |

Every filter is an indexed column on `applications` (no evaluation joins); cursor pagination keeps
page cost flat; the total count is the most expensive part. The core-scenario and pilot runs
(100 applications) list in well under 100 ms.

### 1.2 Query budgets (no N+1)

`backend/tests/integration/test_query_budgets.py` calls each hot endpoint with few and many rows;
the query count must not grow:

| Endpoint | Result |
|---|---|
| HR applicants list | constant (≤ 25 queries per page) |
| HR dashboard summary | constant |
| HR audit events | constant |
| Public job board list | constant (`apps/jobs/tests/test_public_api.py`) |
| Candidate applications list | **was N+1** (2 queries per application: the employer's privacy notice was looked up — with a `get_or_create` — for every row). **Fixed**: one lookup per employer per response (`apps/applications/api/serializers.py`) |

### 1.3 Pilot throughput (in-process)

`run_pilot_benchmark --inline` (one process does extraction, screening and notifications for every
application): 100 applications in 272–423 s on the host, median submission-to-evaluation
2.3 s. The extraction benchmark with 2 sandboxed workers: 100 CVs in 93.5 s. Both well inside
NFR-PERF-02 (15 min); the 4 vCPU / 8 GB worker-profile run is P10-T06.

## 2. End-to-end load (Locust)

Scenarios and pass rules: `loadtests/README.md`. CI: `.github/workflows/load.yml` — job board
(400 users, ≥ 200 RPS), 100 concurrent submissions, HR applicants list (20 users), 1,000 concurrent
submissions; results in the `load-report` artifact (`out/LOAD.md`).

**Run 1 (2026-11-18, gunicorn + uvicorn ASGI workers, as production was configured): failed.**
Job board: 21,000 requests, **69 % HTTP 500**, P95 4.6 s, 117 RPS; logins failed, so the candidate
and HR scenarios could not proceed. Root cause (reproduced locally): under ASGI Django's persistent
connections are not reused across requests - one worker held 57 PostgreSQL connections after 600
requests, so four workers exhausted `max_connections` - and every synchronous view ran on one thread
per worker. Fix: ADR-029 (gunicorn WSGI threaded workers + psycopg connection pool; connections
stayed at 11 under the same local load). Defect D-009 (P0).

**Runs 2-4** fixed the rest: run 2 (ADR-029) removed the 500s; run 3 found the readiness check's
session-level `statement_timeout` leaking into pooled connections (D-010, 12 submit 500s) and a job
board P95 of 1.2 s; run 4 (D-010 fixed, public job board cached for anonymous visitors) was the
first with **zero failed requests**:

| Run 4 (2026-11-18) | Users | Requests | Failures | P95 (list/detail) | Throughput | Result |
|---|---|---|---|---|---|---|
| Job board (1 req/s per user) | 200 | 34,920 | 0 | **160-170 ms** | 195.9 RPS incl. ramp-up | ✅ P95; RPS now measured after ramp-up (210 users) |
| HR applicants list + dashboard | 20 | 1,611 | 0 | **39-56 ms** | 13.5 RPS | ✅ |
| 100 submissions (burst: all within 5 s) | 100 | 900 | 0 | reads 2.2-3.2 s, submit 6.6 s | - | ✅ no failures; latency recorded |
| 1,000 submissions (burst) | 1,000 | 9,000 | 0 | reads 11-49 s, submit 35 s | - | ✅ no failures; **1,100/1,100 submissions recorded** |

**Final run (2026-11-18, `8f62bae`, all checks green):** job board **210.6 RPS, P95 130-140 ms**,
35,607 requests, 0 failures; HR applicants list and dashboard **P95 37-59 ms**, 0 failures; 100 and
1,000 submission bursts 0 failures, **1,100/1,100 submissions recorded**; throughput 100 CVs in
~2.5 min. **NFR-PERF-01 met at pilot load; NFR-PERF-02 met.**

How to read the burst rows: Locust, PostgreSQL, Redis, S3, the API and four Celery workers share one
4-vCPU CI runner, and every candidate starts within seconds, so the runner is saturated by design.
Nothing was lost or failed; latency under a burst like this is a capacity question for production
sizing (dedicated API hosts, more gunicorn workers), not a defect. At pilot load the read budget is
met with a wide margin (job board ~200 RPS at P95 170 ms; HR list P95 < 60 ms).

### 2.1 Throughput (P10-T06) - passed

`load.yml` job *throughput*: the stack capped at 4 vCPU / 8 GB (`infrastructure/perf/compose.throughput.yml`),
100 applications from the whole synthetic corpus through the real workers (`run_pilot_benchmark`):

| Run | Submitting | Processing after the last submission | Submission → evaluation (median / max) | Accounted for |
|---|---|---|---|---|
| 2026-11-17 | 54.5 s | 65.0 s | 48.1 s / 67.5 s | 100 / 100 |
| 2026-11-18 | 59.6 s | 65.0 s | 53.0 s / 66.9 s | 100 / 100 |
| 2026-11-18 (run 4) | 48.5 s | 60.0 s | 48.1 s / 57.9 s | 100 / 100 |
| 2026-11-18 (final) | 69.9 s | 75.0 s | 55.4 s / 75.7 s | 100 / 100 |

About 2 minutes end to end against the NFR-PERF-02 target of 15 minutes.

## 3. Notes

- `LOAD_TEST=true` (development settings only) relaxes per-IP limits because one Locust host
  stands in for many visitors; production keeps them (anonymous 120/min, login 30/min, uploads
  30/hour).
- Found while reviewing limits: allauth's `ACCOUNT_PASSWORD_MIN_LENGTH` was still 10 while the
  password validators require 12 — aligned to 12.
