"""Deterministic Phase 7 advertising optimization checklist."""

from __future__ import annotations

from typing import Any, Iterable, Mapping


ACTION_TYPES = {
    "scale_up": "scale_up_candidate",
    "defend_rank": "core_defense",
    "hold_steady": "next_cycle_review",
    "cautious_test": "new_word_test",
    "continue_observation": "observation_exit_check",
    "optimize_listing": "listing_diagnostic",
    "optimize_bid": "bid_adjustment",
    "optimize_structure": "structure_cleanup",
    "stop_loss": "stop_loss_review",
    "reduce_or_pause": "reduce_or_pause_review",
    "data_missing": "data_completion",
}


def _config_refs(action: str, config: Mapping[str, Any]) -> dict[str, Any]:
    refs: dict[str, Any] = {"config_version": config.get("config_version", config.get("schema_version"))}
    if action in {"stop_loss", "stop_loss_review"}:
        refs["stop_loss"] = config.get("stop_loss")
    elif action in {"defend_rank", "core_defense"}:
        refs["organic_defense"] = config.get("organic_defense")
        refs["acos"] = config.get("acos")
    elif action.startswith("optimize") or action in {"optimize_bid", "optimize_listing", "optimize_structure"}:
        refs["acos"] = config.get("acos")
        refs["diagnostics"] = config.get("diagnostics")
    elif action in {"cautious_test", "continue_observation"}:
        refs["evidence"] = config.get("evidence")
    return refs


def build_optimization_plan(rows: Iterable[Mapping[str, Any]], config: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Create auditable next actions; this function never changes action_group."""
    result: list[dict[str, Any]] = []
    for row in rows:
        action = str(row.get("action_group") or "data_missing")
        result.append({
            "keyword": row.get("keyword"),
            "action_group": action,
            "action_type": ACTION_TYPES.get(action, "manual_review"),
            "ui_conclusion": row.get("ui_conclusion"),
            "data_facts": {key: row.get(key) for key in ("impressions", "clicks", "spend", "orders", "sales", "ctr", "cpc", "cvr", "acos", "roas", "organic_rank", "ad_rank", "market_search_volume", "market_opportunity_score")},
            "rule_hits": list(row.get("rule_hits") or []),
            "config_refs": _config_refs(action, config),
            "next_action_text": row.get("next_action_text"),
            "ai_status": "not_requested",
            "ai_may_change_action": False,
        })
    return result
