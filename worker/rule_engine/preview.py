"""Non-persistent strategy preview / impact calculation."""

from __future__ import annotations

from collections import Counter
from typing import Any, Iterable, Mapping

from worker.rule_engine.engine import evaluate_keyword


def preview_config_impact(rows: Iterable[Mapping[str, Any]], current_config: Mapping[str, Any], temporary_config: Mapping[str, Any]) -> dict[str, Any]:
    changes: list[dict[str, Any]] = []
    before_counts: Counter[str] = Counter()
    after_counts: Counter[str] = Counter()
    for row in rows:
        before = evaluate_keyword(row, current_config)
        after = evaluate_keyword(row, temporary_config)
        before_counts[before["action_group"]] += 1
        after_counts[after["action_group"]] += 1
        if before["action_group"] != after["action_group"] or before["ui_conclusion"] != after["ui_conclusion"]:
            changes.append({"keyword": row.get("keyword"), "before": {"action_group": before["action_group"], "ui_conclusion": before["ui_conclusion"]}, "after": {"action_group": after["action_group"], "ui_conclusion": after["ui_conclusion"]}})
    return {"persisted": False, "changed_count": len(changes), "before_counts": dict(sorted(before_counts.items())), "after_counts": dict(sorted(after_counts.items())), "changes": changes}

