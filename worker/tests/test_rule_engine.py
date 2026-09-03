import unittest

from worker.rule_engine.engine import evaluate_keyword, load_default_config


def keyword(**overrides):
    base = {"keyword": "led light", "impressions": 1000, "clicks": 25, "spend": 10, "sales": 100, "orders": 4, "ctr": 0.025, "cvr": 0.16}
    base.update(overrides)
    return base


class RuleEngineTests(unittest.TestCase):
    def setUp(self):
        self.config = load_default_config()

    def test_missing_data_is_gray(self):
        result = evaluate_keyword(keyword(sales=None), self.config)
        self.assertEqual((result["action_group"], result["ui_conclusion"], result["ui_color"]), ("data_missing", "data_missing", "gray"))

    def test_stop_loss_precedes_market_opportunity(self):
        result = evaluate_keyword(keyword(clicks=30, spend=60, orders=0, sales=0, market_opportunity_score=0.95), self.config)
        self.assertEqual(result["action_group"], "stop_loss")

    def test_defend_is_distinct_from_add(self):
        defend = evaluate_keyword(keyword(organic_rank=5), self.config)
        add = evaluate_keyword(keyword(market_opportunity_score=0.95), self.config)
        self.assertEqual(defend["ui_conclusion"], "defend")
        self.assertEqual(add["ui_conclusion"], "add")
        self.assertNotEqual(defend["action_group"], add["action_group"])

    def test_ai_is_not_called_or_allowed_to_change_action(self):
        result = evaluate_keyword(keyword(market_opportunity_score=0.95), self.config)
        self.assertNotIn("ai_action_group", result)
        self.assertEqual(result["ai_status"], "not_requested")

    def test_report_explanation_fields_are_read_only_and_deterministic(self):
        result = evaluate_keyword(keyword(market_opportunity_score=0.95), self.config)
        self.assertEqual(result["product_stage"], "stable")
        self.assertTrue(result["next_action_text"])
        self.assertIsNone(result["ai_explanation"])
        self.assertIsNone(result["ai_next_action_text"])

    def test_unknown_market_score_is_not_treated_as_zero_or_high(self):
        result = evaluate_keyword(keyword(market_opportunity_score=None), self.config)
        self.assertNotEqual(result["action_group"], "scale_up")
        self.assertNotIn("market_high", result["reason_facts"])

    def test_missing_organic_rank_cannot_trigger_defense(self):
        result = evaluate_keyword(keyword(organic_rank=None), self.config)
        self.assertNotEqual(result["action_group"], "defend_rank")

    def test_zero_sales_keeps_acos_unknown(self):
        result = evaluate_keyword(keyword(sales=0, orders=0, clicks=1, spend=0.5))
        self.assertEqual(result["reason_facts"].get("acos"), None)

    def test_provider_missing_fields_survive_rule_result(self):
        result = evaluate_keyword(keyword(missing_fields=["organic_rank", "suggested_bid"]))
        self.assertEqual(result["missing_fields"], ["organic_rank", "suggested_bid"])

    def test_missing_fields_fixture_is_normalized_without_string_splitting(self):
        result = evaluate_keyword(keyword(missing_fields=" organic_rank "))
        self.assertEqual(result["missing_fields"], ["organic_rank"])

    def test_whitespace_missing_field_is_ignored(self):
        result = evaluate_keyword(keyword(missing_fields=[" ", " organic_rank "]))
        self.assertEqual(result["missing_fields"], ["organic_rank"])


if __name__ == "__main__":
    unittest.main()
