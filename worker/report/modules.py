"""Deterministic Phase 4 report modules; no Amazon write-back or Provider calls."""

from __future__ import annotations

import json
import unicodedata
from typing import Any, Iterable, Mapping


def _stable_row_key(row: Mapping[str, Any]) -> tuple[str, str, str]:
    keyword = str(row.get("keyword") or "")
    normalized = unicodedata.normalize("NFC", keyword)
    return normalized.casefold(), normalized, json.dumps(dict(row), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _positive_rank(value: Any) -> int | None:
    return value if type(value) is int and value > 0 else None


def _finite_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number and number not in (float("inf"), float("-inf")) else None


_MISSING = object()


def normalize_ratio(value: Any, *, denominator: Any = _MISSING, verified_direct: bool = True) -> dict[str, Any]:
    """Normalize a ratio without guessing units or hiding invalid values.

    Provider ratios are decimals (``0.2`` means 20%).  A string with an
    explicit percent sign is accepted as presentation input (``"20%"``), but
    a bare numeric value above 1 is invalid rather than silently treated as a
    percentage.  The original value is always retained for audit display.
    """
    result: dict[str, Any] = {
        "raw_value": value,
        "value": None,
        "display_percent": None,
        "status": "unknown",
        "denominator": None if denominator is _MISSING else denominator,
    }
    denominator_number = _finite_number(denominator) if denominator is not _MISSING and denominator is not None else None
    if value is None or (isinstance(value, str) and not value.strip()):
        if denominator is None or (denominator is _MISSING and not verified_direct) or (denominator is not _MISSING and (denominator_number is None or denominator_number <= 0)):
            result["status"] = "unknown_denominator"
        return result
    explicit_percent = isinstance(value, str) and value.strip().endswith("%")
    candidate_text = value.strip()[:-1] if explicit_percent else value.strip() if isinstance(value, str) else value
    number = _finite_number(candidate_text)
    if number is None:
        result["status"] = "invalid_value"
        return result
    if explicit_percent:
        number /= 100.0
    if not 0 <= number <= 1:
        result["status"] = "invalid_value"
        result["display_percent"] = number * 100
        return result
    if denominator is None or (denominator is _MISSING and not verified_direct) or (denominator is not _MISSING and (denominator_number is None or denominator_number <= 0)):
        result["status"] = "unknown_denominator"
        result["display_percent"] = number * 100
        return result
    result.update({"value": number, "display_percent": number * 100, "status": "valid"})
    return result


def _share_entry(row: Mapping[str, Any], field: str, denominator_field: str) -> dict[str, Any]:
    verified = row.get("share_ratio_verified") is True or row.get(f"{field}_verified") is True
    return normalize_ratio(row.get(field), denominator=row.get(denominator_field, _MISSING), verified_direct=verified)


def build_share_board(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Build the two-denominator share board from explicit provider fields.

    ``keyword_market_share`` and ``asin_keyword_dependency`` are deliberately
    separate from ``traffic_acquisition_rate``.  Missing values stay unknown;
    no share is inferred from rank, clicks, or another denominator.
    """
    output: list[dict[str, Any]] = []
    for source in rows:
        row = dict(source)
        output.append({
            "keyword": row.get("keyword"),
            "asin": row.get("asin") or row.get("my_asin"),
            "period": row.get("share_period") or row.get("period"),
            "scope": row.get("share_scope") or "unknown",
            "keyword_market_share": _share_entry(row, "keyword_market_share", "keyword_market_share_denominator"),
            "asin_keyword_dependency": _share_entry(row, "asin_keyword_dependency", "asin_keyword_dependency_denominator"),
            "traffic_acquisition_rate": _share_entry(row, "traffic_acquisition_rate", "traffic_acquisition_rate_denominator"),
            "source": row.get("provider_source") or row.get("source") or "provider_snapshot",
        })
    return sorted(output, key=_stable_row_key)


def share_module_status(rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    records = list(rows)
    valid_market = sum(item.get("keyword_market_share", {}).get("status") == "valid" for item in records)
    valid_dependency = sum(item.get("asin_keyword_dependency", {}).get("status") == "valid" for item in records)
    identity_complete = bool(records) and all(
        isinstance(item.get("asin"), str) and item.get("asin").strip()
        and isinstance(item.get("period"), str) and item.get("period").strip()
        and item.get("scope") not in (None, "", "unknown")
        and isinstance(item.get("source"), str) and item.get("source").strip()
        for item in records
    )
    complete = bool(records) and identity_complete and valid_market == len(records) and valid_dependency == len(records)
    return {
        "status": "ready" if complete else "partial",
        "reason": "share_denominators_complete" if complete else "share_denominators_incomplete",
        "coverage": {"total_rows": len(records), "keyword_market_share": valid_market, "asin_keyword_dependency": valid_dependency,
                      "identity_complete": sum(bool(item.get("asin") and item.get("period") and item.get("scope") not in (None, "", "unknown")) for item in records)},
    }


def rank_module_status(rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    records = list(rows)
    complete = bool(records) and all(
        _positive_rank(row.get("my_organic_rank")) is not None
        and len(row.get("benchmarks") or []) == 3
        for row in records
    )
    covered = sum(
        _positive_rank(row.get("my_organic_rank")) is not None
        and bool(row.get("benchmarks"))
        for row in records
    )
    return {
        "status": "ready" if complete else "partial",
        "reason": "rank_snapshot_complete" if complete else "rank_snapshot_incomplete",
        "coverage": {"comparable_keywords": covered, "total_keywords": len(records)},
    }


def build_rank_benchmark(rows: Iterable[Mapping[str, Any]], *, my_asin: str | None = None) -> list[dict[str, Any]]:
    """Build Module 02 from already-normalized rank/benchmark records."""
    output: list[dict[str, Any]] = []
    for source in rows:
        row = dict(source)
        own_asin = str(my_asin or row.get("asin") or "").strip().upper() or None
        unique: dict[str, dict[str, Any]] = {}
        for item in (row.get("benchmark_asins") or []):
            if not isinstance(item, Mapping):
                continue
            asin = str(item.get("asin") or "").strip().upper()
            rank = _positive_rank(item.get("organic_rank"))
            if not asin or asin == own_asin or rank is None:
                continue
            candidate = {**dict(item), "asin": asin, "organic_rank": rank}
            previous = unique.get(asin)
            if previous is None or rank < previous["organic_rank"]:
                unique[asin] = candidate
        benchmarks = sorted(unique.values(), key=lambda item: (item["organic_rank"], item["asin"]))[:3]
        my_rank = _positive_rank(row.get("organic_rank"))
        for benchmark in benchmarks:
            benchmark["rank_gap"] = None if my_rank is None else my_rank - benchmark["organic_rank"]
        benchmark = benchmarks[0] if benchmarks else {}
        benchmark_rank = benchmark.get("organic_rank")
        gap = None if my_rank is None or benchmark_rank is None else my_rank - benchmark_rank
        missing = set(row.get("missing_fields") or [])
        if my_rank is None:
            missing.add("my_organic_rank")
        if len(benchmarks) < 3:
            missing.add("benchmark_asins")
        output.append({
            "keyword": row.get("keyword"),
            "my_asin": own_asin,
            "my_organic_rank": my_rank,
            "my_ad_rank": row.get("ad_rank"),
            "benchmarks": benchmarks,
            "benchmark_count": len(benchmarks),
            # Compatibility fields keep old report readers functional.
            "benchmark_asin": benchmark.get("asin"),
            "benchmark_organic_rank": benchmark_rank,
            "rank_gap": gap,
            "rank_change_7d": row.get("rank_change_7d"),
            "rank_change_14d": row.get("rank_change_14d"),
            "rank_change_30d": row.get("rank_change_30d"),
            "weekly_search_volume": row.get("weekly_search_volume"),
            "aba_search_frequency_rank": row.get("aba_search_frequency_rank"),
            "aba_report_from_date": row.get("aba_report_from_date"),
            "aba_report_to_date": row.get("aba_report_to_date"),
            "missing_fields": sorted(missing),
        })
    return sorted(output, key=_stable_row_key)


def build_negative_keywords(rows: Iterable[Mapping[str, Any]], config: Mapping[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """Classify candidates while fail-closed on relevance and phrase scope.

    Relevance is deliberately a supplied business fact.  Missing/unknown
    relevance is never upgraded by ad performance alone.  High spend is the
    inclusive 75th percentile of this report's positive-spend rows, recorded
    on each diagnostic row so the rule remains inspectable and reproducible.
    """
    stop_loss = config["stop_loss"]
    evidence = config["evidence"]
    low_cvr = config.get("diagnostics", {}).get("low_cvr")
    records = [dict(row) for row in rows]
    spends = sorted(float(row["spend"]) for row in records
                    if isinstance(row.get("spend"), (int, float))
                    and not isinstance(row.get("spend"), bool) and float(row["spend"]) > 0)
    if spends:
        position = (len(spends) - 1) * 0.75
        lower, upper = int(position), min(int(position) + 1, len(spends) - 1)
        high_spend_threshold = spends[lower] + (spends[upper] - spends[lower]) * (position - lower)
    else:
        high_spend_threshold = None
    exact: list[dict[str, Any]] = []
    phrase: list[dict[str, Any]] = []
    cautious: list[dict[str, Any]] = []
    pending: list[dict[str, Any]] = []
    low_cvr_high_spend: list[dict[str, Any]] = []
    protected_converted: list[dict[str, Any]] = []

    def candidate(row: Mapping[str, Any], status: str, reason: str, **extra: Any) -> dict[str, Any]:
        relevance = row.get("relevance") if row.get("relevance") in {"related", "unrelated", "unknown"} else "unknown"
        return {**dict(row), "relevance": relevance,
                "relevance_source": row.get("relevance_source") or "not_provided",
                "negative_status": status, "reason": reason,
                "high_spend_threshold": high_spend_threshold,
                "export_eligible": False, **extra}

    for row in records:
        clicks, spend, orders = row.get("clicks"), row.get("spend"), row.get("orders")
        if not all(isinstance(value, (int, float)) and not isinstance(value, bool)
                   for value in (clicks, spend, orders)):
            pending.append(candidate(row, "pending_confirmation", "required_ad_fields_missing"))
            continue
        clicks, spend, orders = float(clicks), float(spend), float(orders)
        relevance = row.get("relevance") if row.get("relevance") in {"related", "unrelated", "unknown"} else "unknown"
        cvr = orders / clicks if clicks > 0 else None
        base = {**row, "cvr_observed": cvr}
        if orders > 0:
            protected_converted.append(candidate(base, "protected_converted", "existing_orders_protected"))
            continue
        hard_stop = clicks >= float(stop_loss["zero_order_clicks"]) and spend >= float(stop_loss["zero_order_spend"])
        if hard_stop and relevance == "unrelated":
            exact.append(candidate(base, "exact_negative_candidate", "zero_orders_and_hard_stop_boundary",
                                   export_eligible=True))
            continue
        if (low_cvr is not None and isinstance(low_cvr, (int, float)) and not isinstance(low_cvr, bool)
                and cvr is not None and cvr < float(low_cvr)
                and high_spend_threshold is not None and spend >= high_spend_threshold):
            low_cvr_high_spend.append(candidate(base, "low_cvr_high_spend", "low_cvr_high_spend_review",
                                                 low_cvr_threshold=float(low_cvr)))
            # Keep one keyword in one operational bucket; this is a diagnostic
            # review, not an additional negative candidate.
            continue
        if relevance == "unknown":
            pending.append(candidate(base, "pending_confirmation", "relevance_unknown"))
        elif relevance == "related":
            cautious.append(candidate(base, "cautious", "related_relevance_protection"))
        elif clicks >= float(evidence["preliminary_clicks_min"]):
            phrase.append(candidate(base, "phrase_negative_candidate", "zero_orders_with_preliminary_evidence",
                                    export_eligible=True))
        elif clicks > 0:
            cautious.append(candidate(base, "cautious", "evidence_insufficient"))
        else:
            pending.append(candidate(base, "pending_confirmation", "no_click_evidence"))

    protected_terms = [str(row.get("keyword") or "").strip().casefold()
                       for row in [*protected_converted, *cautious, *pending, *low_cvr_high_spend]
                       if str(row.get("keyword") or "").strip()]
    safe_phrase: list[dict[str, Any]] = []
    for row in phrase:
        phrase_key = str(row.get("keyword") or "").strip().casefold()
        conflicts = sorted({term for term in protected_terms if term != phrase_key
                             and f" {phrase_key} " in f" {term} "})
        if conflicts:
            pending.append({**row, "negative_status": "pending_confirmation",
                            "reason": "phrase_conflicts_with_protected_keyword",
                            "phrase_conflict_keywords": conflicts, "export_eligible": False})
        else:
            safe_phrase.append(row)

    result = {
        "exact_negative": exact,
        "phrase_negative": safe_phrase,
        "cautious": cautious,
        "pending_confirmation": pending,
        "low_cvr_high_spend": low_cvr_high_spend,
        "protected_converted": protected_converted,
    }
    return {key: sorted(value, key=_stable_row_key) for key, value in result.items()}


def negative_module_status(groups: Mapping[str, Any]) -> dict[str, Any]:
    records = [row for values in groups.values() if isinstance(values, list)
               for row in values if isinstance(row, Mapping)]
    unknown = sum(row.get("relevance") == "unknown" for row in records)
    missing = sum(row.get("reason") == "required_ad_fields_missing" for row in records)
    complete = bool(records) and unknown == 0 and missing == 0
    unclassified = sum(
        row.get("relevance") == "unknown" or row.get("reason") == "required_ad_fields_missing"
        for row in records
    )
    return {
        "status": "ready" if complete else "partial",
        "reason": "negative_classification_complete" if complete else "relevance_or_ad_fields_incomplete",
        "coverage": {"classified_rows": max(0, len(records) - unclassified), "total_rows": len(records)},
    }
