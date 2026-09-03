"""Shared report-0.2 traceability normalization helpers."""

from __future__ import annotations

from typing import Any


def normalise_missing_fields(value: Any) -> list[str]:
    """Return canonical missing-field names without splitting malformed strings."""
    if isinstance(value, str):
        values = (value,)
    elif isinstance(value, (list, tuple, set)):
        values = value
    else:
        values = ()
    return sorted({item.strip() for item in values if isinstance(item, str) and item.strip()})
