"""Tests for config file validation."""

from __future__ import annotations

from pathlib import Path

import yaml

from nepse_trader.config_validation import validate_all, validate_yaml


def _write(path: Path, data: dict) -> Path:
    path.write_text(yaml.dump(data), encoding="utf-8")
    return path


class TestValidateHolidays:
    _SCHEMA: dict = {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "type": "object",
        "properties": {
            "holidays": {
                "type": "array",
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
        },
    }

    def test_valid_holidays(self, tmp_path: Path):
        p = _write(tmp_path / "holidays.yaml", {"holidays": [{"name": "New Year", "month": 1, "day": 1}]})
        assert validate_yaml(p, self._SCHEMA) == []

    def test_missing_required_field(self, tmp_path: Path):
        p = _write(tmp_path / "holidays.yaml", {"holidays": [{"name": "New Year", "month": 1}]})
        errors = validate_yaml(p, self._SCHEMA)
        assert len(errors) >= 1
        assert "day" in errors[0]

    def test_invalid_month(self, tmp_path: Path):
        p = _write(tmp_path / "holidays.yaml", {"holidays": [{"name": "Bad", "month": 13, "day": 1}]})
        errors = validate_yaml(p, self._SCHEMA)
        assert len(errors) >= 1

    def test_empty_file(self, tmp_path: Path):
        p = tmp_path / "empty.yaml"
        p.write_text("", encoding="utf-8")
        errors = validate_yaml(p, self._SCHEMA)
        assert any("empty" in e.lower() for e in errors)

    def test_nonexistent_file(self, tmp_path: Path):
        errors = validate_yaml(tmp_path / "nope.yaml", self._SCHEMA)
        assert any("not found" in e.lower() for e in errors)


class TestValidateSources:
    _SCHEMA: dict = {
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
                            "enabled": {"type": "boolean"},
                            "endpoints": {
                                "type": "object",
                                "patternProperties": {
                                    "^[a-z_]+$": {
                                        "type": "object",
                                        "required": ["url"],
                                        "properties": {
                                            "url": {"type": "string"},
                                            "method": {"type": "string", "pattern": "^(GET|POST)$"},
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

    def test_valid_sources(self, tmp_path: Path):
        data = {
            "sources": {
                "sharesansar": {
                    "enabled": True,
                    "endpoints": {"prices": {"url": "https://example.com/api"}},
                },
            },
        }
        assert validate_yaml(_write(tmp_path / "sources.yaml", data), self._SCHEMA) == []

    def test_endpoint_missing_url(self, tmp_path: Path):
        data = {"sources": {"test": {"endpoints": {"ep": {"method": "GET"}}}}}
        errors = validate_yaml(_write(tmp_path / "sources.yaml", data), self._SCHEMA)
        assert any("url" in e for e in errors)

    def test_bad_method(self, tmp_path: Path):
        data = {"sources": {"test": {"endpoints": {"ep": {"url": "x", "method": "DELETE"}}}}}
        errors = validate_yaml(_write(tmp_path / "sources.yaml", data), self._SCHEMA)
        assert len(errors) >= 1


class TestValidateAll:
    def test_validate_all_runs(self):
        errors = validate_all()
        assert isinstance(errors, list)
