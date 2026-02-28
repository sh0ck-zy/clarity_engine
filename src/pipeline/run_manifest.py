"""
Run manifest: tracks pipeline execution steps, timing, warnings, and artifact hashes.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from pipeline.hashing import compute_file_hash


class RunManifest:
    """Builds a run_manifest.json with step tracking and artifact hashing."""

    def __init__(self, fixture_ref: str, run_id: str) -> None:
        self._run_id = run_id
        self._fixture_ref = fixture_ref
        self._created_at = datetime.now(timezone.utc).isoformat()
        self._steps: list[dict] = []
        self._warnings: list[str] = []
        self._errors: list[str] = []
        self._current_step: Optional[dict] = None

    def step_start(self, name: str) -> None:
        """Begin timing a named step."""
        self._current_step = {
            "name": name,
            "started_at": datetime.now(timezone.utc).isoformat(),
        }

    def step_end(self, name: str, status: str, notes: Optional[str] = None) -> None:
        """End a step with status (ok/warn/error/skipped)."""
        ended_at = datetime.now(timezone.utc)
        if self._current_step and self._current_step["name"] == name:
            started = datetime.fromisoformat(self._current_step["started_at"])
            duration_ms = int((ended_at - started).total_seconds() * 1000)
        else:
            duration_ms = 0

        self._steps.append({
            "name": name,
            "status": status,
            "started_at": self._current_step["started_at"] if self._current_step else ended_at.isoformat(),
            "ended_at": ended_at.isoformat(),
            "duration_ms": duration_ms,
            "notes": notes,
        })
        self._current_step = None

    def add_warning(self, msg: str) -> None:
        self._warnings.append(msg)

    def add_error(self, msg: str) -> None:
        self._errors.append(msg)

    def finalize(self, output_dir: Path) -> dict:
        """
        Compute artifact hashes and build the final manifest dict.

        Scans output_dir for known artifact files and computes their SHA-256 hashes.
        """
        completed_at = datetime.now(timezone.utc).isoformat()
        total_ms = sum(s["duration_ms"] for s in self._steps)

        artifacts = []
        artifact_paths = [
            "facts.json",
            "report.json",
            "drafts/telegram.txt",
            "drafts/telegram.meta.json",
            "drafts/x.txt",
            "drafts/x.meta.json",
        ]
        for rel_path in artifact_paths:
            full = output_dir / rel_path
            if full.exists():
                artifacts.append({
                    "path": rel_path,
                    "sha256": compute_file_hash(full),
                })

        return {
            "schema_version": "1.0",
            "run_id": self._run_id,
            "fixture_ref": self._fixture_ref,
            "created_at": self._created_at,
            "completed_at": completed_at,
            "steps": self._steps,
            "warnings": self._warnings,
            "errors": self._errors,
            "artifacts": artifacts,
            "total_duration_ms": total_ms,
        }

    def save(self, path: Path, manifest: dict) -> None:
        """Write manifest to JSON file."""
        with open(path, "w") as f:
            json.dump(manifest, f, indent=2, ensure_ascii=False)
