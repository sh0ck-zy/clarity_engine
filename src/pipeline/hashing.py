"""
Canonical JSON serialization and SHA-256 hashing for audit trail.

Rules:
- Canonical JSON: sorted keys, compact separators, UTF-8, no ASCII escaping.
- Self-hash: when an artifact contains its own hash field, temporarily set
  that field to "" before hashing, then write the computed hash back.
- Format: "sha256:<hex>"
"""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any


def canonical_json(data: Any) -> bytes:
    """Serialize data to canonical JSON bytes (sorted keys, compact, UTF-8)."""
    return json.dumps(
        data,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    ).encode("utf-8")


def compute_hash(data: dict, self_hash_path: list[str] | None = None) -> str:
    """
    Compute SHA-256 hash of a dict using canonical JSON.

    Args:
        data: Dict to hash.
        self_hash_path: If the dict contains its own hash (e.g. ["provenance", "facts_hash"]),
            temporarily set that field to "" before hashing.

    Returns:
        "sha256:<hex>"
    """
    if self_hash_path:
        data = copy.deepcopy(data)
        _set_nested(data, self_hash_path, "")

    raw = canonical_json(data)
    digest = hashlib.sha256(raw).hexdigest()
    return f"sha256:{digest}"


def compute_file_hash(path: Path) -> str:
    """Compute SHA-256 hash of a file's contents. Returns 'sha256:<hex>'."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return f"sha256:{h.hexdigest()}"


def _set_nested(d: dict, path: list[str], value: Any) -> None:
    """Set a nested dict value by key path."""
    for key in path[:-1]:
        d = d[key]
    d[path[-1]] = value
