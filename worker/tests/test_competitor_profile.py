import unittest

from worker.competitors.profile import build_competitor_profile, competitor_cache_key, validate_competitor_set


class CompetitorProfileTests(unittest.TestCase):
    def test_validates_up_to_three_unique_competitors(self):
        result = validate_competitor_set("B000000001", ["B000000002", "B000000003", "B000000004"])
        self.assertEqual(result["self_asin"], "B000000001")
        with self.assertRaises(ValueError):
            validate_competitor_set("B000000001", ["B000000002", "B000000002", "B000000004"])
        self.assertEqual(validate_competitor_set("B000000001", ["B000000002"])['competitor_asins'], ['B000000002'])
        with self.assertRaises(ValueError):
            validate_competitor_set("B000000001", [f"B00000000{i}" for i in range(2, 6)])

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
        self.assertEqual(profile["module_status"]["status"], "partial")

    def test_preserves_product_metrics_and_self_projection(self):
        profile = build_competitor_profile(
            self_asin="B000000001",
            self_product={"title": "Own", "price": 12.5, "rating": 4.4, "review_count": 99, "variations": [{"size": "100ft"}]},
            competitors=[
                {"asin": "B000000002", "price": 9.5, "currency_code": "USD", "rating": 4.1, "review_count": 20, "bsr": 10, "variation_count": 2, "monthly_sales": 30, "bullet_points": ["A"]},
                {"asin": "B000000003", "title": "B"},
            ],
        )
        self.assertEqual(profile["competitors"][0]["bsr"], 10)
        self.assertNotIn("variations", profile["competitors"][0])
        self.assertIn("variations", profile["competitors"][0]["missing_fields"])
        self.assertEqual(profile["self_product"]["review_count"], 99)
        self.assertEqual(profile["schema_version"], "competitors-0.2")

    def test_cache_key_is_order_independent(self):
        first = competitor_cache_key(marketplace="us", self_asin="B000000001", competitor_asins=["B000000002", "B000000003", "B000000004"], core_keywords=["LED Light", "room decor"])
        second = competitor_cache_key(marketplace="US", self_asin="B000000001", competitor_asins=["B000000004", "B000000002", "B000000003"], core_keywords=["room decor", "led light"])
        self.assertEqual(first, second)

    def test_explicit_selection_allows_five_and_reports_missing_requested_asins(self):
        requested = [f"B00000000{i}" for i in range(2, 7)]
        profile = build_competitor_profile(
            self_asin="B000000001",
            competitors=[{"asin": requested[0], "title": "Only returned"}],
            requested_competitor_asins=requested,
        )
        self.assertEqual(requested, profile["requested_competitor_asins"])
        self.assertEqual(requested[1:], profile["missing_competitor_asins"])
        self.assertEqual("partial", profile["module_status"]["status"])


if __name__ == "__main__":
    unittest.main()
