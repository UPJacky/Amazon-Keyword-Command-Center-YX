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
    # Confirmed ABA fields keep their source period and unit.  Weekly volume
    # must never be silently promoted to a monthly market_search_volume.
    "weekly_search_volume",
    "aba_search_frequency_rank",
    "aba_report_from_date",
    "aba_report_to_date",
    # Rank snapshots are already-normalized inputs from rank-capable tools.
    "benchmark_asins",
    "rank_change_7d",
    "rank_change_14d",
    "rank_change_30d",
}

# Lineage and task identity travel with market facts but are not themselves
# analytical metrics, so absent metadata is not added to missing_fields.
MARKET_PASSTHROUGH_FIELDS = {
    "asin",
    "country",
    "provider_sampled",
    "provider_observations",
}


def merge_market_data(ad_rows: Iterable[Mapping[str, Any]], market_rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    market_by_keyword = {str(row.get("keyword")): row for row in market_rows if row.get("keyword") is not None}
    merged: list[dict[str, Any]] = []
    for ad_row in ad_rows:
        row = deepcopy(dict(ad_row))
        market = market_by_keyword.get(str(row.get("keyword")), {})
        for field in MARKET_FIELDS | MARKET_PASSTHROUGH_FIELDS:
            if field in market:
                # An existing task identity wins over a conflicting provider
                # echo.  The provider value remains inspectable in observations.
                if field == "asin" and row.get(field) not in (None, ""):
                    continue
                row[field] = deepcopy(market[field])
        existing_missing = set(normalise_missing_fields(row.get("missing_fields")))
        existing_missing.update(normalise_missing_fields(market.get("missing_fields")))
        # Explicit provider nulls are unknown values and must remain
        # traceable in the row-level missingness contract.
        existing_missing.update(field for field in MARKET_FIELDS if field in market and market[field] is None)
        row["missing_fields"] = sorted(existing_missing)
        merged.append(row)
    return merged
