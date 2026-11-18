"""Turn a Semgrep JSON report into GitHub annotations; exit 1 when there are findings.

    semgrep scan ... --json -o semgrep.json; python scripts/semgrep_annotations.py semgrep.json
"""

from __future__ import annotations

import json
import sys


def main(path: str) -> int:
    with open(path, encoding="utf-8") as fh:
        report = json.load(fh)
    results = report.get("results", [])
    for r in results:
        rule = r["check_id"].rsplit(".", 1)[-1]
        message = " ".join(r["extra"].get("message", "").split())[:400]
        level = "error" if r["extra"].get("severity") == "ERROR" else "warning"
        where = f"file={r['path']},line={r['start']['line']}"
        sys.stdout.write(f"::{level} {where},title=semgrep {rule}::{message}\n")
    for e in report.get("errors", [])[:10]:
        sys.stdout.write(f"::warning title=semgrep error::{str(e.get('message', e))[:300]}\n")
    sys.stdout.write(f"semgrep: {len(results)} finding(s)\n")
    return 1 if results else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1]))
