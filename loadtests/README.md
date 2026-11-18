# Load tests (P10-T05)

Locust scenarios for NFR-PERF-01 (P95 < 400 ms for list/detail endpoints at pilot load):

| Run | Users | Pass rule |
|---|---|---|
| Job board (`JobBoardUser`, 1 request/s per user) | 210 | every list/detail P95 < 400 ms, ≥ 200 RPS after ramp-up (`--reset-stats`), no failures |
| 100 submissions (`CandidateSubmitter`) | 100 | burst (all within 5 s; stress): no failed request, latency recorded |
| HR applicants list (`HRReviewer`) | 20 | P95 < 400 ms, no failures |
| 1,000 submissions (`CandidateSubmitter`, `LOAD_USER_OFFSET=100`) | 1,000 | stress: no failed request, every submission recorded, latency recorded |

Writes and file transfer (start, upload, attach, answers, submit, login) are reported but not held
to the list/detail budget. `check.py` turns a Locust `--csv` file into a Markdown table and exits 1
on a miss.

CI: `.github/workflows/load.yml` (weekly, on demand, and on pushes touching `loadtests/`) starts
the Docker stack with `LOAD_TEST=true`, seeds demo data, 1,100 synthetic candidates and 100
applications, runs the four scenarios against the API (port 8000) and uploads `out/LOAD.md`.

## Running locally

```bash
echo "LOAD_TEST=true" >> .env        # development settings only: relaxes per-IP limits
docker compose up -d --build
docker compose exec backend python manage.py seed_demo
docker compose exec backend python manage.py seed_load_accounts --count 1100
docker compose exec backend python manage.py seed_core_scenario --count 100
pip install "locust==2.32.4"
DEMO_PASSWORD=... locust -f loadtests/locustfile.py JobBoardUser --headless -u 400 -r 40 -t 3m \
  --host http://127.0.0.1:8000 --csv out/board
python loadtests/check.py out/board_stats.csv --min-rps 200
```

`LOAD_TEST` exists because one Locust machine stands in for many visitors; production keeps the
per-IP limits (anonymous 120/min, login 30/min, uploads 30/hour), which have their own tests.
