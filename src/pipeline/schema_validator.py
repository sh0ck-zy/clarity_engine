"""
Schema validation for Analysis Dossier artifacts.

Validates facts.json, report.json, run_manifest.json, review.json,
and draft metadata against their JSON Schema contracts.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import jsonschema

_SCHEMAS_DIR = Path(__file__).parent / "schemas"

_SCHEMA_CACHE: dict[str, dict] = {}


def _load_schema(schema_name: str) -> dict:
    """Load a JSON Schema by name (without .schema.json suffix)."""
    if schema_name not in _SCHEMA_CACHE:
        path = _SCHEMAS_DIR / f"{schema_name}.schema.json"
        if not path.exists():
            raise FileNotFoundError(f"Schema not found: {path}")
        with open(path) as f:
            _SCHEMA_CACHE[schema_name] = json.load(f)
    return _SCHEMA_CACHE[schema_name]


def validate_artifact(data: dict[str, Any], schema_name: str) -> list[str]:
    """
    Validate a data dict against a named JSON Schema.

    Args:
        data: The artifact data to validate.
        schema_name: Schema file name without extension (e.g. "facts", "report").

    Returns:
        List of validation error messages. Empty list means valid.
    """
    schema = _load_schema(schema_name)
    validator = jsonschema.Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(data), key=lambda e: list(e.absolute_path))
    return [
        f"{'.'.join(str(p) for p in e.absolute_path) or '(root)'}: {e.message}"
        for e in errors
    ]
