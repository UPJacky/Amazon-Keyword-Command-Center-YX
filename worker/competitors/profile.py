"""Deterministic competitor profile and cache-key helpers.

This module only validates and stores user-supplied metadata. It never calls a
Provider and never writes to Amazon.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Iterable, Mapping


ASIN = re.compile(r"^[A-Z0-9]{10}$", re.I)


def _asin(value: str, label: str) -> str:
    if not isinstance(value, str) or not ASIN.fullmatch(value):
        raise ValueError(f"{label} must be a 10-character ASIN")
    return value.upper()


def validate_competitor_set(self_asin: str, competitor_asins: Iterable[str], *, min_count: int = 3, max_count: int = 5) -> dict[str, Any]:
    own = _asin(self_asin, "self_asin")
    competitors = [_asin(value, "competitor_asin") for value in competitor_asins]
    if not min_count <= len(competitors) <= max_count:
        raise ValueError(f"competitor count must be between {min_count} and {max_count}")
    if len(set(competitors)) != len(competitors):
        raise ValueError("competitor ASINs must be unique")
    if own in competitors:
        raise ValueError("self_asin cannot also be a competitor")
    return {"self_asin": own, "competitor_asins": competitors}


def competitor_cache_key(*, marketplace: str, self_asin: str, competitor_asins: Iterable[str], core_keywords: Iterable[str]) -> str:
    contract = validate_competitor_set(self_asin, competitor_asins)
    payload = {"marketplace": marketplace.upper(), "self_asin": contract["self_asin"], "competitor_asins": sorted(contract["competitor_asins"]), "core_keywords": sorted({str(value).strip().casefold() for value in core_keywords if str(value).strip()})}
    return "competitors-" + hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def build_competitor_profile(*, self_asin: str, competitors: Iterable[Mapping[str, Any]], core_keywords: Iterable[str] = (), marketplace: str = "US", snapshot_version: str | None = None) -> dict[str, Any]:
    competitor_rows = list(competitors)
    contract = validate_competitor_set(self_asin, [row.get("asin") for row in competitor_rows])
    by_asin = {str(row.get("asin")).upper(): row for row in competitor_rows}
    rows: list[dict[str, Any]] = []
    for asin in contract["competitor_asins"]:
        source = by_asin[asin]
        rows.append({
            "asin": asin,
            "role": "competitor",
            "brand": source.get("brand"),
            "title": source.get("title"),
            "image_urls": [url for url in (source.get("image_urls") or []) if isinstance(url, str) and url.strip()],
            "core_keywords": sorted({str(value).strip() for value in (source.get("core_keywords") or core_keywords) if str(value).strip()}),
            "missing_fields": sorted(set(source.get("missing_fields") or [])),
        })
    return {
        "schema_version": "competitors-0.1",
        "marketplace": marketplace.upper(),
        "self_asin": contract["self_asin"],
        "competitors": rows,
        "snapshot_version": snapshot_version,
        "cache_key": competitor_cache_key(marketplace=marketplace, self_asin=self_asin, competitor_asins=contract["competitor_asins"], core_keywords=core_keywords),
        "provider_calls": 0,
    }
