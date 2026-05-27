"""Deterministic hashing for cache keys + audit dedupe."""

from __future__ import annotations

import hashlib
import json
from typing import Any


def stable_hash(payload: Any) -> str:
    """SHA-256 hex of a JSON-serialised payload with sorted keys."""
    blob = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()
