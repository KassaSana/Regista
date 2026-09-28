"""Validate a replay export against the committed JSON Schema (tests only)."""

from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator, validate

SCHEMA_PATH = Path(__file__).resolve().parents[2] / "schemas/replay.schema.json"


def validate_export(export: object) -> None:
    """Raise ``jsonschema.ValidationError`` when the export breaks the contract."""
    schema: dict[str, object] = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    validate(
        export,
        schema,
        cls=Draft202012Validator,
        format_checker=Draft202012Validator.FORMAT_CHECKER,
    )
