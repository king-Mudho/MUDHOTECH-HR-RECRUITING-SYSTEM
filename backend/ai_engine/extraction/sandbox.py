"""Run extraction in a separate process with time and memory limits (docs/05 §2, EC-DOC-26).

A crafted PDF can hang or exhaust a parser; the worker must survive. The child is a fresh
``python -m ai_engine.extraction.sandbox`` process (Celery prefork children are daemonic and may
not fork multiprocessing children) that reads the file on stdin and writes the
:class:`ExtractionResult` as JSON on stdout. On POSIX the child gets ``RLIMIT_CPU`` (soft/hard
seconds) and ``RLIMIT_AS``; everywhere the parent enforces a wall-clock timeout and kills it.
"""

from __future__ import annotations

import os
import subprocess  # nosec B404
import sys
from collections.abc import Callable
from pathlib import Path

from ai_engine.contracts import ExtractionResult, Flag
from ai_engine.extraction.extract import extract_document, failed
from ai_engine.extraction.guards import Limits

_PACKAGE_ROOT = Path(__file__).resolve().parents[2]  # directory that contains ai_engine/


def _posix_limits(limits: Limits) -> Callable[[], None]:
    def apply() -> None:  # pragma: no cover - runs in the child on POSIX only
        if sys.platform != "win32":
            import resource

            resource.setrlimit(resource.RLIMIT_CPU, (limits.soft_seconds, limits.hard_seconds))
            resource.setrlimit(resource.RLIMIT_AS, (limits.memory_bytes, limits.memory_bytes))
            resource.setrlimit(resource.RLIMIT_CORE, (0, 0))

    return apply


def run_extraction(
    data: bytes, *, document_id: str, limits: Limits | None = None, ocr: bool = True
) -> ExtractionResult:
    limits = limits or Limits()
    argv = [
        sys.executable,
        "-m",
        "ai_engine.extraction.sandbox",
        document_id,
        str(limits.max_pages),
        str(limits.max_bytes),
        "ocr" if ocr else "no-ocr",
    ]
    env = {
        k: v for k, v in os.environ.items() if k in ("PATH", "SYSTEMROOT", "TEMP", "TMP", "LANG")
    }
    env["PYTHONPATH"] = str(_PACKAGE_ROOT)
    env["PYTHONHASHSEED"] = "0"
    try:
        proc = subprocess.run(  # noqa: S603  # nosec B603
            argv,
            input=data,
            capture_output=True,
            timeout=limits.hard_seconds,
            cwd=_PACKAGE_ROOT,
            env=env,
            preexec_fn=_posix_limits(limits) if os.name == "posix" else None,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return failed("timeout", Flag.TIMEOUT)
    if proc.returncode != 0 or not proc.stdout:
        # killed by RLIMIT_CPU (SIGXCPU) / RLIMIT_AS (MemoryError) / parser crash
        code = "timeout" if proc.returncode in (-24, -9) else "parser_crash"
        return failed(code, Flag.TIMEOUT if code == "timeout" else Flag.CORRUPT)
    try:
        return ExtractionResult.model_validate_json(proc.stdout)
    except ValueError:
        return failed("parser_crash", Flag.CORRUPT)


def _main() -> int:  # pragma: no cover - exercised through run_extraction
    document_id, max_pages, max_bytes = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
    ocr = sys.argv[4] == "ocr"
    data = sys.stdin.buffer.read()
    result = extract_document(
        data,
        document_id=document_id,
        limits=Limits(max_pages=max_pages, max_bytes=max_bytes),
        ocr=ocr,
    )
    sys.stdout.write(result.model_dump_json())
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_main())
