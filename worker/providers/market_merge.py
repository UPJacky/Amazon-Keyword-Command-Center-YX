"""Merge normalized market/rank snapshots into ad aggregates without overwriting ad facts."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Iterable, Mapping

from worker.report.traceability import normalise_missing_fields


MARKET_FIELDS = {
    "organic_rank",
    "ad_rank",
    "top3_asins",
    "top3_click_share",
    "top3_conversion_share",
    "traffic_estimate",
    "traffic_ratio",
    "traffic_acquisition_rate",
    "aba_trend",
    "market_search_volume",
    "competitive_difficulty",
    "suggested_bid",
    "market_opportunity_score",
}


def merge_market_data(ad_rows: Iterable[Mapping[str, Any]], market_rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    market_by_keyword = {str(row.get("keyword")): row for row in market_rows if row.get("keyword") is not None}
    merged: list[dict[str, Any]] = []
    for ad_row in ad_rows:
        row = deepcopy(dict(ad_row))
        market = market_by_keyword.get(str(row.get("keyword")), {})
        for field in MARKET_FIELDS:
            if field in market:
                row[field] = market[field]
        existing_missing = set(normalise_missing_fields(row.get("missing_fields")))
        existing_missing.update(normalise_missing_fields(market.get("missing_fields")))
        # Explicit provider nulls are unknown values and must remain
        # traceable in the row-level missingness contract.
        existing_missing.update(field for field in MARKET_FIELDS if field in market and market[field] is None)
        row["missing_fields"] = sorted(existing_missing)
        merged.append(row)
    return merged
