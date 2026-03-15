"""
Pipeline Trace — observability for the match intelligence pipeline.

Append-only trace of every step in the pipeline.
If a step fails, the pipeline continues; the trace is written at the end.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class TraceStep:
    """A single step in the pipeline trace."""

    name: str           # e.g. "get_team_state:Arsenal"
    source: str         # "tool" | "signal" | "llm" | "validator" | "data_quality"
    duration_ms: int = 0
    success: bool = True
    warnings: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        d = {
            "name": self.name,
            "source": self.source,
            "duration_ms": self.duration_ms,
            "success": self.success,
        }
        if self.warnings:
            d["warnings"] = self.warnings
        if self.metadata:
            d["metadata"] = self.metadata
        return d


class PipelineTrace:
    """Collects trace steps for a single match pipeline run."""

    def __init__(self, match_id: str = ""):
        self.match_id = match_id
        self.steps: List[TraceStep] = []
        self._start_time: Optional[float] = None

    def start(self) -> None:
        """Mark the start of the pipeline."""
        self._start_time = time.time()

    def add_step(
        self,
        name: str,
        source: str,
        duration_ms: int = 0,
        success: bool = True,
        warnings: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Add a completed step to the trace."""
        self.steps.append(TraceStep(
            name=name,
            source=source,
            duration_ms=duration_ms,
            success=success,
            warnings=warnings or [],
            metadata=metadata or {},
        ))

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the trace to a dict for JSON output."""
        total_ms = 0
        if self._start_time:
            total_ms = int((time.time() - self._start_time) * 1000)

        tools_called = [s.name for s in self.steps if s.source == "tool"]
        tools_failed = [s.name for s in self.steps if s.source == "tool" and not s.success]
        all_warnings = []
        for s in self.steps:
            all_warnings.extend(s.warnings)

        return {
            "match_id": self.match_id,
            "total_duration_ms": total_ms,
            "steps": [s.to_dict() for s in self.steps],
            "summary": {
                "total_steps": len(self.steps),
                "tools_called": tools_called,
                "tools_failed": tools_failed,
                "total_warnings": len(all_warnings),
            },
        }

    def summary(self) -> str:
        """Return a 5-line human-readable summary."""
        total = len(self.steps)
        failed = sum(1 for s in self.steps if not s.success)
        warns = sum(len(s.warnings) for s in self.steps)
        total_ms = 0
        if self._start_time:
            total_ms = int((time.time() - self._start_time) * 1000)

        lines = [
            f"Trace: {self.match_id}",
            f"  Steps: {total} ({failed} failed)",
            f"  Warnings: {warns}",
            f"  Duration: {total_ms}ms",
        ]
        # Show failed steps
        for s in self.steps:
            if not s.success:
                lines.append(f"  FAILED: {s.name}")

        return "\n".join(lines)


class TraceContext:
    """Context manager for timing a trace step."""

    def __init__(self, trace: PipelineTrace, name: str, source: str):
        self.trace = trace
        self.name = name
        self.source = source
        self._start: float = 0
        self.warnings: List[str] = []
        self.metadata: Dict[str, Any] = {}
        self.success = True

    def __enter__(self) -> "TraceContext":
        self._start = time.time()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        duration_ms = int((time.time() - self._start) * 1000)
        if exc_type is not None:
            self.success = False
            self.warnings.append(f"Exception: {exc_val}")
        self.trace.add_step(
            name=self.name,
            source=self.source,
            duration_ms=duration_ms,
            success=self.success,
            warnings=self.warnings,
            metadata=self.metadata,
        )
        # Don't suppress exceptions
        return False
