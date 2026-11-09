#!/usr/bin/env python3
"""Edge-case coverage report (docs/09 §2).

For every phase file whose tasks are complete (or the phases passed with --phase), collect the EC
ids listed under the phase's "## Edge cases..." heading (single ids or ranges such as
``EC-ACC-01..08``) and check that each id appears in at least one test file (backend
``test_*.py`` / frontend ``*.test.ts(x)`` / ``e2e/*.spec.ts``).

Usage:
    python scripts/ec_coverage.py                 # phases whose tasks are all ticked
    python scripts/ec_coverage.py --phase 01 02   # explicit phases
    python scripts/ec_coverage.py --all           # every phase (planning view)

Exit code 1 when any EC id of a selected phase is not covered.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EC_RE = re.compile(r"\bEC-[A-Z]+-\d{2,3}\b")
RANGE_RE = re.compile(r"\b(EC-[A-Z]+)-(\d{2,3})\.\.(?:EC-[A-Z]+-)?(\d{2,3})\b")
TASK_RE = re.compile(r"^- \[( |x)\] \*\*P\d\d-T\d\d\*\*", re.MULTILINE)
TEST_GLOBS = [
    "backend/**/test_*.py",
    "backend/**/tests.py",
    "frontend/tests/**/*.test.ts",
    "frontend/tests/**/*.test.tsx",
    "frontend/src/**/*.test.ts",
    "frontend/src/**/*.test.tsx",
    "frontend/e2e/**/*.spec.ts",
]
SKIP_PARTS = {"node_modules", ".venv", ".next"}


def phase_files() -> dict[str, Path]:
    return {p.name[6:8]: p for p in sorted((ROOT / "phases").glob("PHASE_*.md"))}


def expand_ids(text: str) -> set[str]:
    """``EC-ACC-01..03`` -> {EC-ACC-01, EC-ACC-02, EC-ACC-03}; plain ids pass through."""
    ids = set(EC_RE.findall(text))
    for prefix, start, end in RANGE_RE.findall(text):
        width = len(start)
        ids |= {f"{prefix}-{n:0{width}d}" for n in range(int(start), int(end) + 1)}
    return ids


def phase_ec_ids(path: Path) -> set[str]:
    text = path.read_text(encoding="utf-8")
    match = re.search(r"\n## Edge cases[^\n]*\n(.*?)(\n## |\Z)", text, re.DOTALL)
    return expand_ids(match.group(1)) if match else set()


def phase_complete(path: Path) -> bool:
    marks = TASK_RE.findall(path.read_text(encoding="utf-8"))
    return bool(marks) and all(m == "x" for m in marks)


def covered_ids() -> dict[str, list[str]]:
    found: dict[str, list[str]] = {}
    for pattern in TEST_GLOBS:
        for f in ROOT.glob(pattern):
            if SKIP_PARTS.intersection(f.parts):
                continue
            for ec in expand_ids(f.read_text(encoding="utf-8", errors="ignore")):
                found.setdefault(ec, []).append(str(f.relative_to(ROOT)))
    return found


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--phase", nargs="*", help="phase numbers, e.g. 01 02")
    parser.add_argument("--all", action="store_true", help="check every phase")
    args = parser.parse_args(argv)

    phases = phase_files()
    if args.all:
        selected = list(phases)
    elif args.phase:
        selected = [p.zfill(2) for p in args.phase]
    else:
        selected = [n for n, p in phases.items() if phase_complete(p)]

    covered = covered_ids()
    missing_total = 0
    if not selected:
        print("No completed phases selected - nothing to check.")
        return 0
    for number in selected:
        path = phases.get(number)
        if path is None:
            print(f"Phase {number}: no such phase file", file=sys.stderr)
            return 2
        ids = sorted(phase_ec_ids(path))
        missing = [ec for ec in ids if ec not in covered]
        missing_total += len(missing)
        status = "OK" if not missing else f"MISSING {len(missing)}"
        done = len(ids) - len(missing)
        print(f"Phase {number} ({path.name}): {done}/{len(ids)} covered - {status}")
        for ec in missing:
            print(f"    - {ec}")
    return 1 if missing_total else 0


if __name__ == "__main__":
    sys.exit(main())
