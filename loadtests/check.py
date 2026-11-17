"""Check a Locust run against NFR-PERF-01 (P95 < 400 ms for list/detail endpoints).

    python loadtests/check.py out/stats_stats.csv [--budget 400] [--report out/LOAD.md]

File transfer and writes (``upload cv``, ``submit``, ``start``, ``answers``, ``attach cv``,
``login``) are reported but not held to the list/detail budget. Any failed request fails the
check.
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
from pathlib import Path

NOT_BUDGETED = {"upload cv", "submit", "start", "answers", "attach cv", "login", "csrf"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("stats")
    parser.add_argument("--budget", type=float, default=400.0)
    parser.add_argument("--report", default="")
    parser.add_argument("--title", default="Load test")
    parser.add_argument("--min-rps", type=float, default=0.0, help="Aggregated throughput floor")
    args = parser.parse_args(argv)
    with Path(args.stats).open(encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    lines = [
        f"## {args.title}",
        "",
        "| Endpoint | Requests | Failures | Median ms | P95 ms | RPS | Budget |",
        "|---|---|---|---|---|---|---|",
    ]
    problems: list[str] = []
    lines_tail = ""
    for row in rows:
        name = row["Name"]
        if name == "Aggregated":
            rps = float(row["Requests/s"])
            lines_tail = (
                f"Aggregated: {row['Request Count']} requests, {rps:.1f} RPS, P95 {row['95%']} ms"
            )
            if rps < args.min_rps:
                problems.append(f"throughput {rps:.1f} RPS < {args.min_rps:.0f}")
            continue
        p95 = float(row["95%"] or 0)
        failures = int(row["Failure Count"])
        budgeted = name not in NOT_BUDGETED
        ok = (not budgeted or p95 < args.budget) and failures == 0
        lines.append(
            f"| {name} | {row['Request Count']} | {failures} | {row['Median Response Time']} "
            f"| {p95:.0f} | {float(row['Requests/s']):.1f} "
            f"| {('< ' + str(int(args.budget))) if budgeted else 'n/a'} {'✅' if ok else '❌'} |"
        )
        if not ok:
            problems.append(f"{name}: p95 {p95:.0f} ms, {failures} failures")
    text = "\n".join([*lines, "", lines_tail]) + "\n"
    if args.report:
        with Path(args.report).open("a", encoding="utf-8") as fh:
            fh.write(text + "\n")
    sys.stdout.buffer.write(text.encode("utf-8"))
    if os.environ.get("GITHUB_ACTIONS"):  # annotations are readable without downloading artifacts
        for row in rows:
            sys.stdout.write(
                f"::notice title={args.title}::{row['Name']}: {row['Request Count']} req, "
                f"{row['Failure Count']} failed, median {row['Median Response Time']} ms, "
                f"p95 {row['95%']} ms, {float(row['Requests/s']):.1f} rps\n"
            )
        for problem in problems:
            sys.stdout.write(f"::error title={args.title}::{problem}\n")
        # Locust's failure log: what actually went wrong (status codes, error bodies)
        failures = Path(args.stats.replace("_stats.csv", "_failures.csv"))
        if failures.exists():
            with failures.open(encoding="utf-8") as fh:
                for row in list(csv.DictReader(fh))[:10]:
                    sys.stdout.write(
                        f"::error title={args.title} failure::{row.get('Method')} "
                        f"{row.get('Name')} x{row.get('Occurrences')}: "
                        f"{(row.get('Error') or '')[:300]}\n"
                    )
        exceptions = Path(args.stats.replace("_stats.csv", "_exceptions.csv"))
        if exceptions.exists():
            with exceptions.open(encoding="utf-8") as fh:
                for row in list(csv.DictReader(fh))[:5]:
                    message = (row.get("Message") or "").replace("\n", " ")[:300]
                    sys.stdout.write(
                        f"::error title={args.title} exception::x{row.get('Count')}: {message}\n"
                    )
    if problems:
        sys.stderr.write("FAILED: " + "; ".join(problems) + "\n")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
