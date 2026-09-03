"""Normalize Xiyou/ABA-shaped records into the project data dictionary."""

from __future__ import annotations

from typing import Any, Iterable, Mapping


MISSING = None
AD_POSITION_CODES = {"sp", "sb", "sbv"}


def _rank(records: Iterable[Mapping[str, Any]], codes: set[str]) -> int | None:
    values: list[int] = []
    for record in records:
        if record.get("positionCode") not in codes:
            continue
        try:
            values.append(int(record["totalRank"]))
        except (KeyError, TypeError, ValueError):
            continue
    return min(values) if values else MISSING


def normalize_ranks(ranks: Iterable[Mapping[str, Any]] | None) -> dict[str, int | None]:
    records = list(ranks or [])
    return {"organic_rank": _rank(records, {"or"}), "ad_rank": _rank(records, AD_POSITION_CODES)}


def normalize_keyword_record(raw: Mapping[str, Any], *, keyword: str, asin: str) -> dict[str, Any]:
    ranks = normalize_ranks(raw.get("ranks"))
    missing: list[str] = []
    top_asins = raw.get("topAsins")
    if not isinstance(top_asins, list):
        missing.extend(["top3_asins", "top3_click_share", "top3_conversion_share"])
        top_asins = []
    top3 = top_asins[:3]
    top3_click_share = sum(float(item.get("clickShare", 0) or 0) for item in top3 if isinstance(item, Mapping)) if top3 else MISSING
    top3_conversion_share = sum(float(item.get("conversionShare", 0) or 0) for item in top3 if isinstance(item, Mapping)) if top3 else MISSING
    fields = {
        "keyword": keyword,
        "asin": asin,
        **ranks,
        "top3_asins": [item.get("asin") for item in top3 if isinstance(item, Mapping) and item.get("asin")],
        "top3_click_share": top3_click_share,
        "top3_conversion_share": top3_conversion_share,
        "traffic_estimate": raw.get("traffic", MISSING),
        "traffic_ratio": raw.get("trafficRatio", MISSING),
        "traffic_acquisition_rate": raw.get("trafficAcquisitionRate", MISSING),
        "aba_trend": raw.get("abaTrend", MISSING),
    }
    for field in ("organic_rank", "ad_rank"):
        if fields[field] is None:
            missing.append(field)
    for field in ("traffic_estimate", "traffic_ratio", "traffic_acquisition_rate", "aba_trend"):
        if fields[field] is None:
            missing.append(field)
    fields["missing_fields"] = sorted(set(missing))
    return fields

