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

**Status:** the scenarios could not run on the development machine (0.5 GB free RAM; the full
stack plus Locust does not fit). The workflow runs on the first push of `loadtests/` and weekly;
record its P95 table here from the artifact.

| Run | Users | Aggregate RPS | Worst list/detail P95 | Failures | Result |
|---|---|---|---|---|---|
| Job board | 400 | _first CI run_ | | | |
| 100 submissions | 100 | | | | |
| HR applicants list | 20 | | | | |
| 1,000 submissions | 1,000 | | | | |

## 3. Notes

- `LOAD_TEST=true` (development settings only) relaxes per-IP limits because one Locust host
  stands in for many visitors; production keeps them (anonymous 120/min, login 30/min, uploads
  30/hour).
- Found while reviewing limits: allauth's `ACCOUNT_PASSWORD_MIN_LENGTH` was still 10 while the
  password validators require 12 — aligned to 12.
