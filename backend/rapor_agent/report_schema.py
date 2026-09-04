"""Kaydedilen rapor taslağının kanonik JSON sözleşmesi."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator


class ReportDraftSchemaError(ValueError):
    """Rapor taslağının kanonik sözleşmeye uymadığını bildirir."""


@lru_cache(maxsize=1)
def load_report_draft_schema() -> dict[str, Any]:
    path = Path(__file__).resolve().parents[2] / "schemas" / "report-draft.schema.json"
    return json.loads(path.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def report_draft_validator() -> Draft202012Validator:
    return Draft202012Validator(load_report_draft_schema())


def validate_report_draft(draft: dict[str, Any]) -> None:
    errors = sorted(report_draft_validator().iter_errors(draft), key=lambda error: list(error.path))
    if not errors:
        return
    rendered = "; ".join(
        f"{'/'.join(str(part) for part in error.path) or '<root>'}: {error.message}"
        for error in errors
    )
    raise ReportDraftSchemaError(rendered)
