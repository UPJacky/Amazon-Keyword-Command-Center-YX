import unittest

from worker.report.modules import build_negative_keywords, build_rank_benchmark
from worker.rule_engine.engine import load_default_config


class ModuleReportTests(unittest.TestCase):
    def test_rank_benchmark_keeps_unknown_as_none_and_calculates_gap(self):
        result = build_rank_benchmark([
            {"keyword": "led light", "asin": "MY-ASIN", "organic_rank": 5, "ad_rank": 3, "benchmark_asins": [{"asin": "COMP-1", "organic_rank": 2}]},
            {"keyword": "unknown", "organic_rank": None, "ad_rank": None, "benchmark_asins": [{"asin": "COMP-2", "organic_rank": 1}]},
        ], my_asin="MY-ASIN")
        self.assertEqual(result[0]["rank_gap"], 3)
        self.assertIsNone(result[1]["my_organic_rank"])
        self.assertNotEqual(result[1]["my_organic_rank"], 0)

    def test_rank_benchmark_chooses_and_orders_rows_deterministically(self):
        rows = [{
            "keyword": "b",
            "organic_rank": 9,
            "benchmark_asins": [
                {"asin": "COMP-2", "organic_rank": 2},
                {"asin": "COMP-1", "organic_rank": 4},
            ],
        }, {"keyword": "a", "organic_rank": 5, "benchmark_asins": []}]
        reversed_result = build_rank_benchmark(list(reversed(rows)))
        result = build_rank_benchmark(rows)
        self.assertEqual(result, reversed_result)
        self.assertEqual(result[1]["benchmark_asin"], "COMP-1")

    def test_negative_candidates_respect_evidence_and_stop_loss_boundaries(self):
        result = build_negative_keywords([
            {"keyword": "hard", "clicks": 25, "spend": 60, "orders": 0},
            {"keyword": "phrase", "clicks": 12, "spend": 3, "orders": 0},
            {"keyword": "cautious", "clicks": 2, "spend": 1, "orders": 0},
            {"keyword": "converted", "clicks": 30, "spend": 60, "orders": 1},
        ], load_default_config())
        self.assertEqual([row["keyword"] for row in result["exact_negative"]], ["hard"])
        self.assertEqual([row["keyword"] for row in result["phrase_negative"]], ["phrase"])
        self.assertEqual([row["keyword"] for row in result["cautious"]], ["cautious"])
        self.assertEqual(sum(len(items) for items in result.values()), 3)

    def test_negative_candidates_are_order_independent(self):
        rows = [
            {"keyword": "z", "clicks": 2, "spend": 1, "orders": 0},
            {"keyword": "a", "clicks": 25, "spend": 60, "orders": 0},
            {"keyword": "m", "clicks": 12, "spend": 3, "orders": 0},
        ]
        first = build_negative_keywords(rows, load_default_config())
        second = build_negative_keywords(list(reversed(rows)), load_default_config())
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
