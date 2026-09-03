"""Static check that rule actions have stable UI semantics."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MAPPING = ROOT / "rules" / "definitions" / "action_mapping.json"
EXPECTED_ACTIONS = {
    "scale_up", "defend_rank", "hold_steady", "cautious_test", "continue_observation",
    "optimize_listing", "optimize_bid", "optimize_structure", "stop_loss", "reduce_or_pause", "data_missing",
}


def check() -> list[str]:
    if not MAPPING.is_file():
        return ["missing action_mapping.json"]
    data = json.loads(MAPPING.read_text(encoding="utf-8"))
    actions = data.get("action_group_to_ui", {})
    errors = [f"missing action mapping: {name}" for name in sorted(EXPECTED_ACTIONS - set(actions))]
    for name, value in actions.items():
        if not isinstance(value, dict) or not value.get("ui_conclusion") or not value.get("ui_color"):
            errors.append(f"incomplete action mapping: {name}")
    if data.get("display_order") != ["green", "cyan", "yellow", "orange", "red", "gray"]:
        errors.append("display_order does not match the six-color contract")
    return errors


if __name__ == "__main__":
    problems = check()
    if problems:
        raise SystemExit("\n".join(problems))
    print("action_mapping_contract=passed")
