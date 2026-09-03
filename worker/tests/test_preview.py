import unittest

from worker.rule_engine.engine import load_default_config
from worker.rule_engine.preview import preview_config_impact


class PreviewTests(unittest.TestCase):
    def test_preview_is_non_persistent_and_reports_changes(self):
        current = load_default_config()
        temporary = load_default_config()
        temporary["stop_loss"]["zero_order_clicks"] = 5
        rows = [{"keyword": "test", "impressions": 100, "clicks": 5, "spend": 60, "sales": 0, "orders": 0}]
        result = preview_config_impact(rows, current, temporary)
        self.assertFalse(result["persisted"])
        self.assertEqual(result["changed_count"], 1)
        self.assertEqual(result["changes"][0]["before"]["action_group"], "continue_observation")
        self.assertEqual(result["changes"][0]["after"]["action_group"], "stop_loss")


if __name__ == "__main__":
    unittest.main()
