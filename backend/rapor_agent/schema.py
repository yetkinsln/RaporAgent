"""Kanonik JSON Schema'yi uygulamanin tek alan sozlesmesi olarak kullanir."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator


class CanonicalSchemaError(ValueError):
    """Kanonik vaka cikarisinin schema ile uyusmadigini bildirir."""


@lru_cache(maxsize=1)
def load_schema() -> dict[str, Any]:
    schema_path = Path(__file__).resolve().parents[2] / "schemas" / "case-extraction.schema.json"
    return json.loads(schema_path.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def validator() -> Draft202012Validator:
    return Draft202012Validator(load_schema())


def validate_extraction(extraction: dict[str, Any]) -> None:
    errors = sorted(validator().iter_errors(extraction), key=lambda error: list(error.path))
    if not errors:
        return

    rendered = "; ".join(
        f"{'/'.join(str(part) for part in error.path) or '<root>'}: {error.message}"
        for error in errors
    )
    raise CanonicalSchemaError(rendered)
