"""Engine versioning and deterministic input hashing (completed in P07-T08)."""

from __future__ import annotations

import hashlib
import json
from typing import Any

ENGINE_VERSION = "0.1.0"


def input_hash(payload: Any) -> str:
    """Stable SHA-256 over canonical JSON (sorted keys, no whitespace)."""
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
