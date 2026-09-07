import unittest

from worker.providers.market_merge import merge_market_data


class MarketMergeTests(unittest.TestCase):
    def test_market_fields_supplement_without_overwriting_ad_metrics(self):
        rows = merge_market_data(
            [{"keyword": "led light", "clicks": 131, "spend": 82.96, "missing_fields": []}],
            [{"keyword": "led light", "organic_rank": 5, "market_opportunity_score": 0.9, "missing_fields": ["aba_trend"]}],
        )
        self.assertEqual(rows[0]["clicks"], 131)
        self.assertEqual(rows[0]["spend"], 82.96)
        self.assertEqual(rows[0]["organic_rank"], 5)
        self.assertEqual(rows[0]["missing_fields"], ["aba_trend"])

    def test_unknown_keyword_is_not_invented(self):
        rows = merge_market_data([{"keyword": "unknown", "clicks": 0}], [{"keyword": "other", "organic_rank": 1}])
        self.assertNotIn("organic_rank", rows[0])

    def test_explicit_provider_null_is_listed_as_missing(self):
        rows = merge_market_data(
            [{"keyword": "led light", "missing_fields": []}],
            [{"keyword": "led light", "organic_rank": None, "suggested_bid": None}],
        )
        self.assertIsNone(rows[0]["organic_rank"])
        self.assertIsNone(rows[0]["suggested_bid"])
        self.assertEqual(rows[0]["missing_fields"], ["organic_rank", "suggested_bid"])

    def test_missing_fields_fixture_is_normalized_without_string_splitting(self):
        rows = merge_market_data(
            [{"keyword": "led light", "missing_fields": "spend"}],
            [{"keyword": "led light", "missing_fields": [" organic_rank ", "spend", 7, " "]}],
        )
        self.assertEqual(rows[0]["missing_fields"], ["organic_rank", "spend"])

    def test_whitespace_missing_field_is_ignored(self):
        rows = merge_market_data([{"keyword": "led light"}], [{"keyword": "led light", "missing_fields": [" "]}])
        self.assertEqual(rows[0]["missing_fields"], [])

    def test_rank_aba_and_lineage_fields_survive_without_overwriting_ad_identity(self):
        benchmarks = [{"asin": "B000000002", "organic_rank": 2}]
        observations = {"abaReport": {"weeklySearchVolume": 1200}}
        row = merge_market_data(
            [{"keyword": "led light", "asin": "B000000001", "clicks": 10}],
            [{"keyword": "led light", "asin": "B999999999", "country": "US",
              "organic_rank": 5, "benchmark_asins": benchmarks,
              "rank_change_7d": -2, "rank_change_14d": 1, "rank_change_30d": None,
              "weekly_search_volume": 1200, "aba_search_frequency_rank": 42,
              "aba_report_from_date": "2026-08-23", "aba_report_to_date": "2026-08-29",
              "provider_sampled": True, "provider_observations": observations,
              "missing_fields": ["rank_change_30d"]}],
        )[0]
        self.assertEqual("B000000001", row["asin"])
        self.assertEqual(benchmarks, row["benchmark_asins"])
        self.assertEqual(1200, row["weekly_search_volume"])
        self.assertEqual(42, row["aba_search_frequency_rank"])
        self.assertEqual(observations, row["provider_observations"])
        self.assertEqual(["rank_change_30d"], row["missing_fields"])


if __name__ == "__main__":
    unittest.main()
