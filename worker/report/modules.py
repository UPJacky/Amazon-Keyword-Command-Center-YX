"""Deterministic Phase 4 report modules; no Amazon write-back or Provider calls."""

from __future__ import annotations

import json
import unicodedata
from typing import Any, Iterable, Mapping


def _stable_row_key(row: Mapping[str, Any]) -> tuple[str, str, str]:
    keyword = str(row.get("keyword") or "")
    normalized = unicodedata.normalize("NFC", keyword)
    return normalized.casefold(), normalized, json.dumps(dict(row), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def build_rank_benchmark(rows: Iterable[Mapping[str, Any]], *, my_asin: str | None = None) -> list[dict[str, Any]]:
    """Build Module 02 from already-normalized rank/benchmark records."""
    output: list[dict[str, Any]] = []
    for source in rows:
        row = dict(source)
        benchmarks = [item for item in (row.get("benchmark_asins") or []) if isinstance(item, Mapping)]
        if my_asin:
            benchmarks = [item for item in benchmarks if item.get("asin") != my_asin]
        benchmark = min(
            benchmarks,
            key=lambda item: (
                str(item.get("asin") or ""),
                json.dumps(dict(item), ensure_ascii=False, sort_keys=True, separators=(",", ":")),
            ),
        ) if benchmarks else {}
        my_rank = row.get("organic_rank")
        benchmark_rank = benchmark.get("organic_rank")
        gap = None if my_rank is None or benchmark_rank is None else int(my_rank) - int(benchmark_rank)
        output.append({
            "keyword": row.get("keyword"),
            "my_asin": my_asin or row.get("asin"),
            "my_organic_rank": my_rank,
            "my_ad_rank": row.get("ad_rank"),
            "benchmark_asin": benchmark.get("asin"),
            "benchmark_organic_rank": benchmark_rank,
            "rank_gap": gap,
            "rank_change_7d": row.get("rank_change_7d"),
            "rank_change_14d": row.get("rank_change_14d"),
            "rank_change_30d": row.get("rank_change_30d"),
            "missing_fields": sorted(set(row.get("missing_fields") or []) | ({"benchmark_organic_rank"} if benchmark and benchmark_rank is None else set())),
        })
    return sorted(output, key=_stable_row_key)


def build_negative_keywords(rows: Iterable[Mapping[str, Any]], config: Mapping[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """Classify negative-keyword candidates without ever executing them."""
    stop_loss = config["stop_loss"]
    evidence = config["evidence"]
    exact: list[dict[str, Any]] = []
    phrase: list[dict[str, Any]] = []
    cautious: list[dict[str, Any]] = []
    pending: list[dict[str, Any]] = []
    for source in rows:
        row = dict(source)
        clicks = row.get("clicks")
        spend = row.get("spend")
        orders = row.get("orders")
        if clicks is None or spend is None or orders is None:
            pending.append({**row, "negative_status": "pending_confirmation", "reason": "required_ad_fields_missing"})
            continue
        clicks = float(clicks)
        spend = float(spend)
        orders = float(orders)
        candidate = {**row, "negative_status": None, "reason": None}
        if orders > 0:
            continue
        if clicks >= float(stop_loss["zero_order_clicks"]) and spend >= float(stop_loss["zero_order_spend"]):
            exact.append({**candidate, "negative_status": "exact_negative_candidate", "reason": "zero_orders_and_hard_stop_boundary"})
        elif clicks >= float(evidence["preliminary_clicks_min"]):
            phrase.append({**candidate, "negative_status": "phrase_negative_candidate", "reason": "zero_orders_with_preliminary_evidence"})
        elif clicks > 0:
            cautious.append({**candidate, "negative_status": "cautious", "reason": "evidence_insufficient"})
        else:
            pending.append({**candidate, "negative_status": "pending_confirmation", "reason": "no_click_evidence"})
    return {
        "exact_negative": sorted(exact, key=_stable_row_key),
        "phrase_negative": sorted(phrase, key=_stable_row_key),
        "cautious": sorted(cautious, key=_stable_row_key),
        "pending_confirmation": sorted(pending, key=_stable_row_key),
    }
