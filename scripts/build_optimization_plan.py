#!/usr/bin/env python3
"""Build a deterministic, auditable Phase 7 optimization artifact."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from worker.diagnostics.optimization import build_optimization_plan
from worker.rule_engine.engine import load_default_config


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    report = json.loads(Path(args.report).read_text(encoding="utf-8"))
    payload = {
        "schema_version": "optimization-plan-0.2",
        "ai_may_change_action": False,
        "entity_diagnosis_contract": "entity_context_required_for_judgement",
        "actions": build_optimization_plan(report["rows"], load_default_config()),
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps({"passed": True, "actions": len(payload["actions"]), "ai_may_change_action": False}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
