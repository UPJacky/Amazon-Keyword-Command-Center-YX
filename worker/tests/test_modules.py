import unittest

from worker.report.modules import build_negative_keywords, build_rank_benchmark, rank_module_status
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
        self.assertEqual(result[1]["benchmark_asin"], "COMP-2")

    def test_rank_benchmark_selects_three_ranked_unique_competitors(self):
        result = build_rank_benchmark([{
            "keyword": "led light", "asin": "B000000001", "organic_rank": 7,
            "weekly_search_volume": 1200, "aba_report_from_date": "2026-08-23",
            "aba_report_to_date": "2026-08-29",
            "benchmark_asins": [
                {"asin": "B000000004", "organic_rank": 3, "title": "fourth"},
                {"asin": "B000000001", "organic_rank": 1},
                {"asin": "B000000003", "organic_rank": 2, "title": "third"},
                {"asin": "B000000002", "organic_rank": 2, "title": "second"},
                {"asin": "B000000005", "organic_rank": None},
                {"asin": "B000000004", "organic_rank": 8},
            ],
        }], my_asin="B000000001")[0]
        self.assertEqual(["B000000002", "B000000003", "B000000004"],
                         [item["asin"] for item in result["benchmarks"]])
        self.assertEqual([5, 5, 4], [item["rank_gap"] for item in result["benchmarks"]])
        self.assertEqual("B000000002", result["benchmark_asin"])
        self.assertEqual(1200, result["weekly_search_volume"])
        self.assertEqual([], result["missing_fields"])
        self.assertEqual("ready", rank_module_status([result])["status"])

    def test_rank_benchmark_marks_incomplete_without_inventing_positions(self):
        result = build_rank_benchmark([{
            "keyword": "unknown", "organic_rank": "4", "benchmark_asins": [
                {"asin": "B000000002", "organic_rank": 0},
                {"asin": "B000000003", "organic_rank": "2"},
            ],
        }], my_asin="B000000001")[0]
        self.assertIsNone(result["my_organic_rank"])
        self.assertEqual([], result["benchmarks"])
        self.assertEqual(["benchmark_asins", "my_organic_rank"], result["missing_fields"])
        self.assertEqual("partial", rank_module_status([result])["status"])

    def test_negative_candidates_respect_evidence_and_stop_loss_boundaries(self):
        result = build_negative_keywords([
            {"keyword": "hard", "clicks": 25, "spend": 60, "orders": 0, "relevance": "unrelated"},
            {"keyword": "phrase", "clicks": 12, "spend": 3, "orders": 0, "relevance": "unrelated"},
            {"keyword": "cautious", "clicks": 2, "spend": 1, "orders": 0, "relevance": "related"},
            {"keyword": "converted", "clicks": 30, "spend": 60, "orders": 1, "relevance": "unrelated"},
        ], load_default_config())
        self.assertEqual([row["keyword"] for row in result["exact_negative"]], ["hard"])
        self.assertEqual([row["keyword"] for row in result["phrase_negative"]], ["phrase"])
        self.assertEqual([row["keyword"] for row in result["cautious"]], ["cautious"])
        self.assertEqual(sum(len(items) for items in result.values()), 4)
        self.assertEqual("protected_converted", result["protected_converted"][0]["negative_status"])

    def test_negative_relevance_and_low_cvr_protection_are_explicit(self):
        result = build_negative_keywords([
            {"keyword": "related term", "clicks": 30, "spend": 20, "orders": 0, "relevance": "related", "relevance_source": "user"},
            {"keyword": "unknown term", "clicks": 30, "spend": 1, "orders": 0},
            {"keyword": "expensive", "clicks": 10, "spend": 90, "orders": 0, "relevance": "unrelated"},
            {"keyword": "cheap", "clicks": 10, "spend": 1, "orders": 0, "relevance": "unrelated"},
        ], load_default_config())
        self.assertEqual(["related term"], [row["keyword"] for row in result["cautious"]])
        self.assertEqual(["unknown term"], [row["keyword"] for row in result["pending_confirmation"]])
        self.assertEqual(["expensive"], [row["keyword"] for row in result["low_cvr_high_spend"]])
        self.assertEqual([], result["exact_negative"])
        self.assertEqual(["cheap"], [row["keyword"] for row in result["phrase_negative"]])
        self.assertEqual("user", result["cautious"][0]["relevance_source"])

    def test_phrase_candidate_conflicting_with_converted_term_is_not_exportable(self):
        result = build_negative_keywords([
            {"keyword": "led", "clicks": 10, "spend": 1, "orders": 0, "relevance": "unrelated"},
            {"keyword": "led lights", "clicks": 1, "spend": 10, "orders": 1, "relevance": "related"},
        ], load_default_config())
        self.assertEqual([], result["phrase_negative"])
        self.assertEqual("phrase_conflicts_with_protected_keyword", result["pending_confirmation"][0]["reason"])
        self.assertFalse(result["pending_confirmation"][0]["export_eligible"])

    def test_negative_candidates_are_order_independent(self):
        rows = [
            {"keyword": "z", "clicks": 2, "spend": 1, "orders": 0, "relevance": "related"},
            {"keyword": "a", "clicks": 25, "spend": 60, "orders": 0, "relevance": "unrelated"},
            {"keyword": "m", "clicks": 12, "spend": 3, "orders": 0, "relevance": "unrelated"},
        ]
        first = build_negative_keywords(rows, load_default_config())
        second = build_negative_keywords(list(reversed(rows)), load_default_config())
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
