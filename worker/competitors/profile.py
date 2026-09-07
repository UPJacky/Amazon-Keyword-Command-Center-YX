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

# Keep the comparison vocabulary explicit so provider fields are not silently
# discarded while still preventing arbitrary non-report metadata from leaking
# into the public projection.
PRODUCT_FIELDS = (
    "brand", "title", "main_image_url", "image_urls", "price", "currency_code",
    "rating", "review_count", "monthly_sales", "category", "bsr", "variation_count",
    "variations", "bullet_points", "video_count", "aplus", "storefront",
    "core_keywords", "source", "source_url", "sampled_at", "provider_sampled",
)
COMPARISON_FIELDS = (
    "brand", "title", "main_image_url", "price", "rating", "review_count",
    "monthly_sales", "category", "bsr", "variation_count", "variations",
    "bullet_points",
)


def _asin(value: str, label: str) -> str:
    if not isinstance(value, str) or not ASIN.fullmatch(value):
        raise ValueError(f"{label} must be a 10-character ASIN")
    return value.upper()


def validate_competitor_set(self_asin: str, competitor_asins: Iterable[str], *, min_count: int = 0, max_count: int = 3) -> dict[str, Any]:
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


def _project_product(source: Mapping[str, Any], asin: str, *, role: str, core_keywords: Iterable[str]) -> dict[str, Any]:
    row: dict[str, Any] = {"asin": asin, "role": role}
    for field in PRODUCT_FIELDS:
        if field not in source:
            continue
        value = source[field]
        if field in {"image_urls", "core_keywords", "bullet_points"}:
            if isinstance(value, list):
                row[field] = [item for item in value if isinstance(item, str) and item.strip()]
            else:
                row[field] = []
        else:
            row[field] = value
    if "core_keywords" not in row:
        row["core_keywords"] = []
    row["core_keywords"] = sorted({str(value).strip() for value in (row["core_keywords"] or core_keywords) if str(value).strip()})
    if "image_urls" not in row:
        row["image_urls"] = []
    missing = {str(value) for value in (source.get("missing_fields") or []) if isinstance(value, str) and value.strip()}
    for field in COMPARISON_FIELDS:
        if field == "main_image_url" and row.get("main_image_url"):
            continue
        if field == "main_image_url" and row.get("image_urls"):
            continue
        if row.get(field) is None or row.get(field) == "" or row.get(field) == []:
            missing.add(field)
    row["missing_fields"] = sorted(missing)
    return row


def build_competitor_profile(*, self_asin: str, competitors: Iterable[Mapping[str, Any]], core_keywords: Iterable[str] = (), marketplace: str = "US", snapshot_version: str | None = None, self_product: Mapping[str, Any] | None = None) -> dict[str, Any]:
    competitor_rows = list(competitors)
    contract = validate_competitor_set(self_asin, [row.get("asin") for row in competitor_rows])
    by_asin = {str(row.get("asin")).upper(): row for row in competitor_rows}
    rows: list[dict[str, Any]] = []
    for asin in contract["competitor_asins"]:
        source = by_asin[asin]
        rows.append(_project_product(source, asin, role="competitor", core_keywords=core_keywords))
    projected_self = None
    if isinstance(self_product, Mapping):
        projected_self = _project_product(self_product, contract["self_asin"], role="self", core_keywords=core_keywords)
    missing_competitors = len(rows) < 3
    missing_fields = sorted({field for row in rows for field in row.get("missing_fields", [])})
    status = "partial" if missing_competitors or missing_fields or projected_self is None else "ready"
    reason = "need_up_to_three_competitors" if missing_competitors else ("missing_product_fields" if missing_fields else "competitor_snapshot_complete")
    return {
        "schema_version": "competitors-0.2",
        "module_status": {"status": status, "reason": reason},
        "marketplace": marketplace.upper(),
        "self_asin": contract["self_asin"],
        "competitors": rows,
        "self_product": projected_self,
        "missing_fields": missing_fields,
        "snapshot_version": snapshot_version,
        "cache_key": competitor_cache_key(marketplace=marketplace, self_asin=self_asin, competitor_asins=contract["competitor_asins"], core_keywords=core_keywords),
        "provider_calls": 0,
    }
