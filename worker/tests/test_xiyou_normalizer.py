import unittest

from worker.providers.xiyou_normalizer import normalize_keyword_record, normalize_ranks


class XiyouNormalizerTests(unittest.TestCase):
    def test_rank_semantics_use_minimum_rank_by_position_code(self):
        result = normalize_ranks([
            {"positionCode": "or", "totalRank": 10},
            {"positionCode": "or", "totalRank": 4},
            {"positionCode": "sp", "totalRank": 8},
            {"positionCode": "sb", "totalRank": 3},
        ])
        self.assertEqual(result, {"organic_rank": 4, "ad_rank": 3})

    def test_missing_rank_is_none_not_zero_and_top3_is_normalized(self):
        result = normalize_keyword_record({"topAsins": [{"asin": "A", "clickShare": 0.4, "conversionShare": 0.3}, {"asin": "B", "clickShare": 0.2, "conversionShare": 0.1}]}, keyword="led", asin="SELF")
        self.assertIsNone(result["organic_rank"])
        self.assertIsNone(result["ad_rank"])
        self.assertEqual(result["top3_asins"], ["A", "B"])
        self.assertIn("organic_rank", result["missing_fields"])
        self.assertNotEqual(result["organic_rank"], 0)


if __name__ == "__main__":
    unittest.main()

