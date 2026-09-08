"""Build auditable feature-by-ASIN text evidence matrices."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Iterable, Mapping


def _texts(product: Mapping[str, Any]) -> tuple[dict[str, Any], ...]:
    rows: list[dict[str, Any]] = []
    if product.get("title") is not None:
        rows.append({"text": str(product["title"]), "location": "title", "index": 0})
    bullets = product.get("bullet_points")
    if isinstance(bullets, list):
        rows.extend({"text": str(value), "location": "bullet", "index": index} for index, value in enumerate(bullets) if str(value).strip())
    attributes = product.get("attributes")
    if isinstance(attributes, Mapping):
        rows.extend({"text": f"{key}: {value}", "location": "attribute", "index": index} for index, (key, value) in enumerate(attributes.items()) if str(value).strip())
    return tuple(rows)


def _needle(feature: Mapping[str, Any]) -> tuple[str, ...]:
    values = [feature.get("name"), feature.get("english_name"), *(feature.get("keywords") or [])]
    return tuple(str(value).strip().casefold() for value in values if str(value).strip())


def build_text_evidence_matrix(features: Iterable[Mapping[str, Any]], products: Iterable[Mapping[str, Any]], *, confirmed_feature_ids: Iterable[str], confirmation_version: str) -> dict[str, Any]:
    """Create one cell for every confirmed feature and supplied ASIN.

    A quote is emitted only when it is an exact substring of archived product
    text.  No quote or final product-quality ranking is invented here.
    """
    feature_rows = [dict(item) for item in features]
    by_id = {str(item.get("feature_id")): item for item in feature_rows if item.get("feature_id") is not None}
    ids = [str(value) for value in confirmed_feature_ids]
    if not ids or len(set(ids)) != len(ids) or any(value not in by_id for value in ids):
        raise ValueError("confirmed feature ids must be unique and belong to the snapshot")
    product_rows = [dict(item) for item in products]
    asins = [str(item.get("asin") or "").upper() for item in product_rows]
    if not asins or len(set(asins)) != len(asins) or any(not asin for asin in asins):
        raise ValueError("products must contain unique ASINs")
    cells: list[dict[str, Any]] = []
    for feature_id in ids:
        feature = by_id[feature_id]
        needles = _needle(feature)
        for product, asin in zip(product_rows, asins):
            text_rows = _texts(product)
            if not text_rows:
                status = "source_missing"
                quotes: list[dict[str, Any]] = []
            else:
                matches = [row for row in text_rows if any(needle in row["text"].casefold() for needle in needles)]
                status = "mentioned" if matches else "not_mentioned"
                quotes = [{"quote": row["text"], "location": row["location"], "index": row["index"]} for row in matches]
            cells.append({
                "feature_id": feature_id,
                "asin": asin,
                "status": status,
                "quotes": quotes,
                "source_refs": deepcopy(product.get("source_refs") or []),
                "evidence_version": confirmation_version,
            })
    return {
        "schema_version": "feature-text-evidence-0.1",
        "confirmation_version": confirmation_version,
        "feature_ids": ids,
        "asins": asins,
        "cells": cells,
        "status": "ready" if all(cell["status"] != "source_missing" for cell in cells) else "partial",
        "provider_calls": 0,
    }
