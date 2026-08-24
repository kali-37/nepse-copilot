"""Config file validation using JSON Schema.

Provides validation functions for the YAML config files (sources, holidays, cost model).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from nepse_trader.config import CONFIG_DIR

_HOLIDAYS_SCHEMA: dict[str, Any] = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "type": "object",
    "properties": {
        # ``null`` is valid for both lists: a key whose entries are all commented
        # out parses as null, and ``load_holidays`` already reads that as "empty"
        # (``raw.get(...) or []``). Rejecting it here would fail the file this
        # repository ships.
        "holidays": {
            "type": ["array", "null"],
            "items": {
                "type": "object",
                "required": ["name", "month", "day"],
                "properties": {
                    "name": {"type": "string"},
                    "month": {"type": "integer", "minimum": 1, "maximum": 12},
                    "day": {"type": "integer", "minimum": 1, "maximum": 31},
                },
            },
        },
        "ranges": {
            "type": ["array", "null"],
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "start_month": {"type": "integer"},
                    "start_day": {"type": "integer"},
                    "end_month": {"type": "integer"},
                    "end_day": {"type": "integer"},
                },
            },
        },
    },
}

_SOURCES_SCHEMA: dict[str, Any] = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "type": "object",
    "properties": {
        "sources": {
            "type": "object",
            "patternProperties": {
                "^[a-z_]+$": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "base_url": {"type": "string"},
                        "access_method": {"type": "string"},
                        "requires_auth": {"type": "boolean"},
                        "enabled": {"type": "boolean"},
                        "rate_limit_seconds": {"type": "number", "exclusiveMinimum": 0},
                        "notes": {"type": "string"},
                        "endpoints": {
                            "type": "object",
                            "patternProperties": {
                                "^[a-z_]+$": {
                                    "type": "object",
                                    "required": ["url"],
                                    "properties": {
                                        "url": {"type": "string"},
                                        "method": {"type": "string", "pattern": "^(GET|POST)$"},
                                        "params": {"type": "object"},
                                        "headers": {"type": "object"},
                                        "confidence": {"type": "string"},
                                        "notes": {"type": "string"},
                                    },
                                },
                            },
                        },
                    },
                },
            },
        },
    },
}


def _validate(data: Any, schema: dict[str, Any], path: Path) -> list[str]:
    errors: list[str] = []
    try:
        import jsonschema
    except ImportError:
        return ["jsonschema not installed; run 'pip install jsonschema' to enable schema validation"]
    validator = jsonschema.Draft7Validator(schema)
    for err in validator.iter_errors(data):
        loc = " → ".join(str(p) for p in err.absolute_path) if err.absolute_path else "(root)"
        errors.append(f"  {path.name}:{loc}: {err.message}")
    return errors


def validate_yaml(path: Path, schema: dict[str, Any]) -> list[str]:
    """Validate a single YAML file against its JSON Schema.

    Returns a (possibly empty) list of human-readable error messages.
    """
    if not path.exists():
        return [f"  {path.name}: file not found"]
    try:
        with path.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
    except yaml.YAMLError as e:
        return [f"  {path.name}: invalid YAML — {e}"]
    if data is None:
        return [f"  {path.name}: empty file"]
    return _validate(data, schema, path)


def validate_all() -> list[str]:
    """Validate all config files. Returns list of error messages (empty = OK)."""
    errors: list[str] = []
    errors.extend(validate_yaml(CONFIG_DIR / "holidays.yaml", _HOLIDAYS_SCHEMA))
    errors.extend(validate_yaml(CONFIG_DIR / "sources.yaml", _SOURCES_SCHEMA))
    return errors
