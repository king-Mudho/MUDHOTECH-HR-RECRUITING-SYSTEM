#!/usr/bin/env bash
# Lighthouse (mobile preset, default throttling): median of N runs per URL.
# Phase 03 exit criterion: Performance >= 85, Accessibility >= 95, SEO >= 95 on /jobs and /jobs/[slug].
#
#   CHROME_PATH="C:/Program Files/Google/Chrome/Application/chrome.exe" \
#     scripts/lighthouse.sh 3 http://localhost:3000/jobs http://localhost:3000/jobs/<slug>
#
# Run against a production build (`npm run build && npm run start`), never `next dev`.
set -euo pipefail
N=${1:?runs}; shift
OUT=$(mktemp -d)
for url in "$@"; do
  curl -s -o /dev/null "$url" # warm the 60 s data cache
  for i in $(seq 1 "$N"); do
    npx --yes lighthouse@13.5.0 "$url" --quiet --chrome-flags="--headless=new" \
      --only-categories=performance,accessibility,seo,best-practices --output=json \
      --output-path="$OUT/run-$i.json" >/dev/null 2>&1
  done
  python - "$url" "$N" "$OUT" <<'PY'
import json, statistics, sys
url, n, out = sys.argv[1], int(sys.argv[2]), sys.argv[3]
runs = [json.load(open(f"{out}/run-{i}.json", encoding="utf-8")) for i in range(1, n + 1)]
scores = {k: [round(r["categories"][k]["score"] * 100) for r in runs] for k in runs[0]["categories"]}
print(url, {k: (statistics.median(v), v) for k, v in scores.items()})
PY
done
rm -rf "$OUT"
