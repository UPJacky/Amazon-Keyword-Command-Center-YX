"""Small deterministic V1 keyword action engine."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from worker.report.traceability import normalise_missing_fields


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = ROOT / "rules" / "defaults" / "stable.json"
MAPPING_PATH = ROOT / "rules" / "definitions" / "action_mapping.json"
NEXT_ACTIONS = {
    "scale_up": "逐步加投并观察自然位与整体利润",
    "defend_rank": "保持防守投放，复核自然位与成本边界",
    "hold_steady": "保持当前策略，进入下一周期复盘",
    "cautious_test": "小预算试投，补充点击与转化证据",
    "continue_observation": "继续观察，不做强动作",
    "optimize_listing": "优先检查 Listing、主图与转化承接",
    "optimize_bid": "调整竞价并复核 CPC / ACOS",
    "optimize_structure": "检查广告结构、匹配方式与搜索词隔离",
    "stop_loss": "暂停或止损，确认无订单原因",
    "reduce_or_pause": "降低预算或暂停，等待新证据",
    "data_missing": "补齐缺失数据后再判定",
}


def load_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _ratio(value: Any) -> float | None:
    return None if value is None else float(value)


def load_default_config() -> dict[str, Any]:
    return load_json(DEFAULT_CONFIG_PATH)


def evaluate_keyword(keyword: Mapping[str, Any], config: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Evaluate one aggregated keyword without consulting AI or a Provider."""
    cfg = config or load_default_config()
    missing = [field for field in ("keyword", "impressions", "clicks", "spend", "sales", "orders") if keyword.get(field) is None]
    if missing:
        return _result(keyword, cfg, "data_missing", ["required_fields_missing"], {"missing_fields": missing})

    clicks = float(keyword["clicks"])
    orders = float(keyword["orders"])
    spend = float(keyword["spend"])
    sales = float(keyword["sales"])
    acos = None if sales == 0 else spend / sales
    ctr = _ratio(keyword.get("ctr"))
    cvr = _ratio(keyword.get("cvr"))
    evidence_cfg = cfg["evidence"]
    if orders >= evidence_cfg["sufficient_orders_min"] or clicks >= evidence_cfg["sufficient_clicks_min"]:
        evidence = "sufficient"
    elif orders >= evidence_cfg["preliminary_orders_min"] or clicks >= evidence_cfg["preliminary_clicks_min"]:
        evidence = "preliminary"
    else:
        evidence = "insufficient"

    market_score = keyword.get("market_opportunity_score")
    market_high = market_score is not None and float(market_score) >= cfg["market"]["high_opportunity_min"]
    organic_rank = keyword.get("organic_rank")
    defense = organic_rank is not None and float(organic_rank) <= cfg["organic_defense"]["core_max_rank"]
    cost_healthy = acos is not None and acos <= cfg["acos"]["tolerance"]
    defense_cost_healthy = (
        acos is not None
        and acos <= float(cfg["organic_defense"].get("max_defense_acos", cfg["acos"]["tolerance"]))
    )
    hard_stop = orders == 0 and clicks >= cfg["stop_loss"]["zero_order_clicks"] and spend >= cfg["stop_loss"]["zero_order_spend"]

    if hard_stop:
        return _result(keyword, cfg, "stop_loss", ["zero_order_hard_stop"], {"clicks": clicks, "spend": spend, "evidence": evidence})
    if defense and defense_cost_healthy:
        return _result(keyword, cfg, "defend_rank", ["organic_rank_in_defense_zone", "cost_within_defense_boundary"], {"organic_rank": organic_rank, "acos": acos, "evidence": evidence})
    if evidence == "insufficient":
        action = "cautious_test" if market_high else "continue_observation"
        return _result(keyword, cfg, action, ["evidence_insufficient"], {"market_high": market_high, "evidence": evidence})
    if market_high and not cost_healthy:
        diagnostic = "optimize_listing" if cvr is not None and cvr < cfg["diagnostics"]["low_cvr"] else "optimize_bid"
        return _result(keyword, cfg, diagnostic, ["high_opportunity_cost_not_healthy"], {"market_high": True, "acos": acos, "ctr": ctr, "cvr": cvr, "evidence": evidence})
    if market_high and cost_healthy and evidence == "sufficient":
        return _result(keyword, cfg, "scale_up", ["sufficient_evidence_high_opportunity"], {"market_high": True, "acos": acos, "evidence": evidence})
    if evidence == "sufficient" and acos is not None and not cost_healthy and market_score is None:
        return _result(keyword, cfg, "data_missing", ["market_opportunity_score_missing_for_high_cost_case"], {"acos": acos, "evidence": evidence, "missing_fields": ["market_opportunity_score"]})
    return _result(keyword, cfg, "hold_steady", ["no_higher_priority_rule_hit"], {"evidence": evidence, "acos": acos})


def _result(keyword: Mapping[str, Any], config: Mapping[str, Any], action: str, hits: list[str], facts: dict[str, Any]) -> dict[str, Any]:
    mapping = load_json(MAPPING_PATH)["action_group_to_ui"][action]
    missing_fields = normalise_missing_fields(
        list(normalise_missing_fields(keyword.get("missing_fields")))
        + list(normalise_missing_fields(facts.get("missing_fields")))
    )
    return {
        "keyword": keyword.get("keyword"),
        "keyword_role": keyword.get("keyword_role"),
        "product_stage": config.get("product_stage"),
        "effective_config_version": config.get("config_version", config.get("schema_version", "unknown")),
        "action_group": action,
        "ui_conclusion": mapping["ui_conclusion"],
        "ui_color": mapping["ui_color"],
        "rule_hits": hits,
        "reason_facts": facts,
        "missing_fields": missing_fields,
        "evidence_level": facts.get("evidence", "insufficient"),
        "next_action_text": NEXT_ACTIONS.get(action, "补充证据后复盘"),
        "ai_explanation": None,
        "ai_next_action_text": None,
        "ai_status": "not_requested"
    }
