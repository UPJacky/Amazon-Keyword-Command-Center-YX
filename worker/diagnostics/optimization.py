"""Deterministic Phase 7 advertising optimization checklist."""

from __future__ import annotations

from typing import Any, Iterable, Mapping

from worker.rule_engine.engine import evaluate_keyword


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

ENTITY_FIELDS = (
    "campaign_id", "campaign_name", "ad_group_id", "ad_group_name",
    "target_id", "target", "match_type", "targeting_type", "ad_type",
)
REQUIRED_ENTITY_GROUPS = (
    ("campaign_id", "campaign_name"),
    ("ad_group_id", "ad_group_name"),
    ("target_id", "target"),
    ("match_type",),
)
ENTITY_METRIC_FIELDS = ("impressions", "clicks", "spend", "orders", "sales")


def _present(value: Any) -> bool:
    return value is not None and not isinstance(value, bool) and str(value).strip() != ""


def _entity_contexts(row: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Return only entity fields supplied by the source; never infer target from keyword."""
    raw = row.get("ad_entities", row.get("entity_contexts"))
    candidates = raw if isinstance(raw, list) else []
    if not candidates and any(_present(row.get(field)) for field in ENTITY_FIELDS):
        candidates = [row]
    contexts: list[dict[str, Any]] = []
    seen: set[str] = set()
    for candidate in candidates:
        if not isinstance(candidate, Mapping):
            continue
        context = {field: candidate.get(field) for field in ENTITY_FIELDS if _present(candidate.get(field))}
        # Metrics are part of the entity fact, not keyword-level fallbacks.
        # Preserve explicit nulls as missing evidence and never copy row facts.
        for field in ENTITY_METRIC_FIELDS:
            if field in candidate:
                context[field] = candidate.get(field)
        if not context:
            continue
        signature = repr(sorted(context.items()))
        if signature not in seen:
            seen.add(signature)
            contexts.append(context)
    return contexts


def _entity_diagnosis(row: Mapping[str, Any], data_facts: Mapping[str, Any], action: str,
                      rule_hits: list[str], next_action: Any) -> tuple[list[dict[str, Any]], str, list[str]]:
    contexts = _entity_contexts(row)
    if not contexts:
        contexts = [{}]
    diagnoses: list[dict[str, Any]] = []
    statuses: list[str] = []
    missing_union: set[str] = set()
    for context in contexts:
        missing: list[str] = []
        for group in REQUIRED_ENTITY_GROUPS:
            if not any(_present(context.get(field)) for field in group):
                missing.append("/".join(group))
        missing_metrics = [field for field in ENTITY_METRIC_FIELDS if not _present(context.get(field))]
        missing.extend(missing_metrics)
        ready = not missing
        entity_status = "ready" if ready else ("partial" if context else "not_available")
        statuses.append(entity_status)
        missing_union.update(missing)
        entity_evaluation = None
        if ready:
            entity_input = {"keyword": row.get("keyword")}
            for field in ("market_opportunity_score", "organic_rank", "keyword_role"):
                if field in row:
                    entity_input[field] = row.get(field)
            entity_input.update({field: context.get(field) for field in ENTITY_METRIC_FIELDS})
            entity_evaluation = evaluate_keyword(entity_input, row.get("config") if isinstance(row.get("config"), Mapping) else None)
        if ready and entity_evaluation and entity_evaluation["action_group"] != "data_missing":
            judgement = {
                "status": "judged",
                "conclusion": entity_evaluation["ui_conclusion"],
                "action_group": entity_evaluation["action_group"],
                "basis": entity_evaluation["rule_hits"],
            }
            recommendation = {
                "status": "ready",
                "action_group": entity_evaluation["action_group"],
                "action_type": ACTION_TYPES.get(entity_evaluation["action_group"], "manual_review"),
                "text": entity_evaluation["next_action_text"],
            }
        else:
            judgement = {
                "status": "not_judged",
                "conclusion": "不可判定",
                "reason": "ad_entity_context_missing" if not ready else "keyword_action_not_confirmed",
            }
            recommendation = {
                "status": "pending",
                "action_group": "data_missing",
                "action_type": ACTION_TYPES["data_missing"],
                "text": "补齐广告活动、广告组、投放目标和匹配类型后再判断实体级动作",
            }
        supplied_exit = row.get("exit_condition", row.get("exit_conditions"))
        exit_condition = ({"status": "ready", "value": supplied_exit}
                          if ready and _present(supplied_exit)
                          else {"status": "pending", "value": "补齐广告实体与观察窗口后定义退出条件"})
        entity_facts = {key: context.get(key) for key in (*ENTITY_METRIC_FIELDS, "ctr", "cpc", "cvr", "acos", "roas") if key in context}
        diagnoses.append({
            "entity_context": context,
            "entity_status": entity_status,
            "missing_fields": missing,
            "facts": entity_facts,
            "judgement": judgement,
            "recommended_action": recommendation,
            "exit_condition": exit_condition,
            "entity_evaluation": entity_evaluation,
        })
    overall = "ready" if statuses and all(status == "ready" for status in statuses) else ("partial" if any(status == "partial" for status in statuses) else "not_available")
    return diagnoses, overall, sorted(missing_union)


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
        data_facts = {key: row.get(key) for key in ("impressions", "clicks", "spend", "orders", "sales", "ctr", "cpc", "cvr", "acos", "roas", "organic_rank", "ad_rank", "market_search_volume", "market_opportunity_score")}
        rule_hits = list(row.get("rule_hits") or [])
        diagnoses, entity_status, missing_entity_fields = _entity_diagnosis(
            row, data_facts, action, rule_hits, row.get("next_action_text"),
        )
        result.append({
            "keyword": row.get("keyword"),
            "action_group": action,
            "action_type": ACTION_TYPES.get(action, "manual_review"),
            "ui_conclusion": row.get("ui_conclusion"),
            "data_facts": data_facts,
            "rule_hits": rule_hits,
            "config_refs": _config_refs(action, config),
            "next_action_text": row.get("next_action_text"),
            "observation_window": row.get("observation_window"),
            "exit_conditions": row.get("exit_conditions", row.get("exit_condition")),
            "entity_contexts": [diagnosis["entity_context"] for diagnosis in diagnoses if diagnosis["entity_context"]],
            "entity_status": entity_status,
            "missing_entity_fields": missing_entity_fields,
            "entity_diagnoses": diagnoses,
            "ai_status": "not_requested",
            "ai_may_change_action": False,
        })
    return result


def optimization_module_status(actions: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Describe whether every action has the entity evidence it needs."""
    records = list(actions)
    ready = bool(records) and all(
        row.get("entity_status") == "ready"
        and bool(row.get("entity_diagnoses"))
        and all(isinstance(item, Mapping)
                and item.get("judgement", {}).get("status") == "judged"
                and item.get("recommended_action", {}).get("status") == "ready"
                and item.get("exit_condition", {}).get("status") == "ready"
                for item in row.get("entity_diagnoses") or [])
        for row in records
    )
    return {
        "status": "ready" if ready else "partial",
        "reason": "entity_judgement_complete" if ready else "entity_context_or_exit_incomplete",
        "coverage": {"total_actions": len(records),
                      "entity_ready_actions": sum(row.get("entity_status") == "ready" for row in records)},
    }
