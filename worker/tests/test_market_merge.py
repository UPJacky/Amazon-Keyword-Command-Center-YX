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


if __name__ == "__main__":
    unittest.main()
