import unittest

from worker.competitors.profile import build_competitor_profile, competitor_cache_key, validate_competitor_set


class CompetitorProfileTests(unittest.TestCase):
    def test_validates_three_to_five_unique_competitors(self):
        result = validate_competitor_set("B000000001", ["B000000002", "B000000003", "B000000004"])
        self.assertEqual(result["self_asin"], "B000000001")
        with self.assertRaises(ValueError):
            validate_competitor_set("B000000001", ["B000000002", "B000000002", "B000000004"])
        with self.assertRaises(ValueError):
            validate_competitor_set("B000000001", ["B000000002"])

    def test_profile_preserves_images_keywords_and_no_provider_calls(self):
        profile = build_competitor_profile(
            self_asin="B000000001",
            competitors=[
                {"asin": "B000000002", "brand": "A", "image_urls": ["https://img/1.jpg"], "core_keywords": ["led light"]},
                {"asin": "B000000003", "missing_fields": ["title"]},
                {"asin": "B000000004", "title": "C"},
            ],
            core_keywords=["room decor"],
            snapshot_version="fixture-v1",
        )
        self.assertEqual(profile["provider_calls"], 0)
        self.assertEqual(profile["competitors"][0]["image_urls"], ["https://img/1.jpg"])
        self.assertIn("room decor", profile["competitors"][1]["core_keywords"])
        self.assertEqual(profile["snapshot_version"], "fixture-v1")

    def test_cache_key_is_order_independent(self):
        first = competitor_cache_key(marketplace="us", self_asin="B000000001", competitor_asins=["B000000002", "B000000003", "B000000004"], core_keywords=["LED Light", "room decor"])
        second = competitor_cache_key(marketplace="US", self_asin="B000000001", competitor_asins=["B000000004", "B000000002", "B000000003"], core_keywords=["room decor", "led light"])
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
