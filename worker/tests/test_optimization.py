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

    def test_entity_diagnosis_preserves_context_and_has_four_audit_parts(self):
        row = {
            "keyword": "led light", "action_group": "defend_rank", "ui_conclusion": "defend",
            "rule_hits": ["organic_rank_in_defense_zone"], "next_action_text": "保持自然位防守",
            "clicks": 10, "impressions": 100,
            "ad_entities": [{"campaign_name": "Campaign A", "ad_group_name": "Group A", "target": "led light", "match_type": "精准", "impressions": 100, "clicks": 10, "spend": 1, "orders": 2, "sales": 10}],
        }
        result = build_optimization_plan([row], load_default_config())[0]
        self.assertEqual(result["entity_status"], "ready")
        diagnosis = result["entity_diagnoses"][0]
        self.assertEqual(diagnosis["judgement"]["status"], "judged")
        self.assertEqual(diagnosis["recommended_action"]["status"], "ready")
        self.assertEqual(diagnosis["exit_condition"]["status"], "pending")
        self.assertEqual(diagnosis["entity_context"]["match_type"], "精准")
        self.assertEqual(diagnosis["facts"]["spend"], 1)

    def test_entity_metrics_are_independent_and_identity_only_is_not_judged(self):
        row = {
            "keyword": "led light", "action_group": "defend_rank", "ui_conclusion": "defend",
            "ad_entities": [
                {"campaign_name": "A", "ad_group_name": "GA", "target": "led light", "match_type": "精准", "impressions": 100, "clicks": 10, "spend": 10, "orders": 10, "sales": 100},
                {"campaign_name": "B", "ad_group_name": "GB", "target": "led light", "match_type": "词组", "impressions": 100, "clicks": 10, "spend": 100, "orders": 0, "sales": 0},
            ],
        }
        result = build_optimization_plan([row], load_default_config())[0]
        self.assertEqual([item["facts"]["spend"] for item in result["entity_diagnoses"]], [10, 100])
        self.assertEqual([item["judgement"]["status"] for item in result["entity_diagnoses"]], ["judged", "judged"])
        identity_only = build_optimization_plan([{"keyword": "led light", "action_group": "defend_rank", "ui_conclusion": "defend", "ad_entities": [{"campaign_name": "A", "ad_group_name": "GA", "target": "led light", "match_type": "精准"}]}], load_default_config())[0]
        self.assertEqual(identity_only["entity_diagnoses"][0]["judgement"]["status"], "not_judged")

    def test_missing_entity_context_is_not_judged_and_does_not_infer_from_keyword(self):
        result = build_optimization_plan([{"keyword": "led light", "action_group": "scale_up"}], load_default_config())[0]
        self.assertEqual(result["entity_status"], "not_available")
        diagnosis = result["entity_diagnoses"][0]
        self.assertEqual(diagnosis["judgement"]["status"], "not_judged")
        self.assertEqual(diagnosis["recommended_action"]["action_group"], "data_missing")
        self.assertNotIn("target", diagnosis["entity_context"])


if __name__ == "__main__":
    unittest.main()
