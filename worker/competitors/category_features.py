"""Normalize category-feature snapshots without inventing or discarding facts.

The external provider schema is intentionally treated as an input boundary.  A
snapshot may use the tutorial's names (``analysis_results`` and
``product_feature``) or the already-normalized ``features`` list.  This module
does not call a provider and does not decide that a feature is irrelevant just
because the product currently lacks it.
"""

from __future__ import annotations

from copy import deepcopy
import re
from typing import Any, Iterable, Mapping


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        if isinstance(value, str):
            match = re.match(r"^\s*(-?(?:\d+(?:\.\d+)?|\.\d+))\s*%?", value)
            if not match:
                return None
            value = match.group(1)
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if result == result and result not in (float("inf"), float("-inf")) else None


def _share(value: Any) -> tuple[float | None, float | None]:
    """Return (percentage-points, decimal ratio) without guessing silently.

    Sorftime samples commonly use ``64.2%`` or ``64.2`` for percentage
    points. A numeric value in [0, 1] is treated as an already-normalized
    ratio. Both representations are retained explicitly in the artifact.
    """
    number = _number(value)
    if number is None or number < 0:
        return None, None
    explicit_percent = isinstance(value, str) and "%" in value
    if explicit_percent or number >= 1:
        return number, number / 100.0 if number <= 100 else None
    return number * 100.0, number


def _first(source: Mapping[str, Any], *names: str) -> Any:
    for name in names:
        if name in source:
            return source[name]
    return None


def _feature_source(payload: Mapping[str, Any]) -> list[Any] | None:
    for name in ("features", "product_feature", "analysis_results"):
        value = payload.get(name)
        if isinstance(value, list):
            return value
    return None


def normalize_category_features(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Return a stable, auditable feature snapshot.

    Empty/missing arrays are structural failures, not a successful zero-feature
    result.  Invalid individual rows are retained as ``invalid_rows`` so the
    caller can show a partial/error state rather than silently dropping them.
    """
    if not isinstance(payload, Mapping):
        raise ValueError("category feature response must be an object")
    raw = _feature_source(payload)
    if raw is None:
        raise ValueError("category feature response is missing a feature array")
    if not raw:
        raise ValueError("category feature response contains an empty feature array")

    features: list[dict[str, Any]] = []
    invalid_rows: list[int] = []
    empty_name_count = 0
    for index, item in enumerate(raw):
        if not isinstance(item, Mapping):
            invalid_rows.append(index)
            continue
        name = _first(item, "feature_name", "product_feature", "name", "feature")
        name = str(name).strip() if name is not None else ""
        if not name:
            empty_name_count += 1
            continue
        feature_id = _first(item, "feature_id", "id")
        feature_id = str(feature_id).strip() if feature_id is not None and str(feature_id).strip() else f"feature-{index + 1:03d}"
        product_share_raw = _first(item, "product_count_share", "productCountShare", "count_share")
        sales_share_raw = _first(item, "monthly_sales_share", "monthlySalesShare", "sales_share")
        product_count_share, product_count_share_ratio = _share(product_share_raw)
        monthly_sales_share, monthly_sales_share_ratio = _share(sales_share_raw)
        description = _first(item, "feature_description", "description", "desc")
        row = {
            "feature_id": feature_id,
            "name": name,
            "feature_description": str(description).strip() if description is not None and str(description).strip() else None,
            "product_count_share_raw": deepcopy(product_share_raw),
            "product_count_share": product_count_share,
            "product_count_share_ratio": product_count_share_ratio,
            "monthly_sales_share_raw": deepcopy(sales_share_raw),
            "monthly_sales_share": monthly_sales_share,
            "monthly_sales_share_ratio": monthly_sales_share_ratio,
            "ratio": product_count_share_ratio,
            "source_index": index,
            "source_refs": deepcopy(_first(item, "source_refs", "sources")) if isinstance(_first(item, "source_refs", "sources"), list) else [],
        }
        features.append(row)

    if not features:
        raise ValueError("category feature response has no valid feature rows")

    ordered = sorted(
        features,
        key=lambda row: (
            row["monthly_sales_share"] is None,
            -(row["monthly_sales_share"] or 0),
            row["source_index"],
            row["feature_id"],
        ),
    )
    return {
        "schema_version": "category-features-0.1",
        "features": ordered,
        "feature_count": len(ordered),
        "empty_name_count": empty_name_count,
        "invalid_rows": invalid_rows,
        "source": str(payload.get("source") or "provider_snapshot"),
        "snapshot_version": payload.get("snapshot_version"),
        "provider_calls": int(payload.get("provider_calls") or 0),
    }


def build_feature_cleaning_draft(snapshot: Mapping[str, Any], *, self_facts: Iterable[str] = ()) -> dict[str, Any]:
    """Create a review draft; ``exclude`` is never inferred from missing facts."""
    features = snapshot.get("features") if isinstance(snapshot, Mapping) else None
    if not isinstance(features, list) or not features:
        raise ValueError("cannot draft category features without a normalized snapshot")
    facts = {str(value).strip().casefold() for value in self_facts if str(value).strip()}
    items: list[dict[str, Any]] = []
    for feature in features:
        name = str(feature.get("name") or "").strip()
        present = name.casefold() in facts
        items.append({
            "feature_id": feature["feature_id"],
            "name": name,
            "product_count_share": feature.get("product_count_share"),
            "product_count_share_ratio": feature.get("product_count_share_ratio"),
            "monthly_sales_share": feature.get("monthly_sales_share"),
            "monthly_sales_share_ratio": feature.get("monthly_sales_share_ratio"),
            "proposal": "keep" if present else "gap",
            "reason": "confirmed_in_product_facts" if present else "category_feature_not_confirmed_in_current_facts",
            "confirmed": False,
        })
    return {
        "schema_version": "category-feature-draft-0.1",
        "status": "draft",
        "items": items,
        "confirmed_version": None,
        "provider_calls": 0,
    }


def category_feature_module_status(snapshot: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(snapshot, Mapping):
        return {"status": "not_generated", "reason": "category_feature_snapshot_missing"}
    features = snapshot.get("features")
    if not isinstance(features, list) or not features:
        return {"status": "failed", "reason": "category_feature_structure_invalid"}
    if snapshot.get("invalid_rows") or snapshot.get("empty_name_count"):
        return {"status": "partial", "reason": "category_feature_rows_need_review"}
    return {"status": "ready", "reason": "category_feature_snapshot_complete"}
