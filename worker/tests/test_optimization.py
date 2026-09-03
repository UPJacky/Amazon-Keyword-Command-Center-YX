import json
import unittest
from pathlib import Path

from worker.diagnostics.optimization import build_optimization_plan
from worker.rule_engine.engine import load_default_config


ROOT = Path(__file__).resolve().parents[2]


class OptimizationTests(unittest.TestCase):
    def test_each_action_is_traceable_to_facts_rules_and_config(self):
        report = json.loads((ROOT / "data" / "golden" / "market-demo-report" / "master-table.json").read_text(encoding="utf-8"))
        actions = build_optimization_plan(report["rows"][:10], load_default_config())
        self.assertEqual(len(actions), 10)
        for action in actions:
            self.assertIn("data_facts", action)
            self.assertIn("rule_hits", action)
            self.assertIn("config_refs", action)
            self.assertFalse(action["ai_may_change_action"])

    def test_stop_loss_uses_stop_loss_config_reference(self):
        result = build_optimization_plan([{"keyword": "bad", "action_group": "stop_loss", "rule_hits": ["zero_order_hard_stop"]}], load_default_config())[0]
        self.assertEqual(result["action_type"], "stop_loss_review")
        self.assertIn("stop_loss", result["config_refs"])


if __name__ == "__main__":
    unittest.main()
