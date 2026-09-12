import json
import unittest

from worker.competitors.category_features import normalize_category_features
from worker.providers.sorftime_adapter import SorftimeCallBudget, SorftimeCatalogAdapter, normalize_category_feature_response, normalize_product_detail


def result(data):
    return {"content": [{"type": "text", "text": json.dumps({"doc": {}, "data": data})}]}


class FakeTransport:
    def __init__(self):
        self.calls = []

    def call(self, name, arguments):
        self.calls.append((name, arguments))
        if name == "product_detail":
            return result({"asin": arguments["asin"], "brand": "Brand", "title": "Title", "main_image": ["https://img.example/a.jpg"], "price": 9.99, "star_rating": 4.5, "review_count": 12, "monthly_sales_volume": 30, "category": "LED Lights", "variation_count": 2})
        if name == "similar_product_feature":
            return result({"analysis_results": [{"product_feature": "调光", "product_count_share": "64.2% (5/19)", "monthly_sales_share": "28.47%", "feature_description": "dimmable"}]})
        raise AssertionError(name)


class SorftimeAdapterTests(unittest.TestCase):
    def test_real_product_shape_maps_to_competitor_fields(self):
        row = normalize_product_detail(result({"asin": "B000000001", "brand": "Brand", "title": "Title", "main_image": ["https://img.example/a.jpg"], "price": 9.99, "star_rating": 4.5, "review_count": 12, "monthly_sales_volume": 30, "category": "LED Lights", "variation_count": 2}), asin="B000000001", marketplace="US")
        self.assertEqual("B000000001", row["asin"])
        self.assertEqual(["https://img.example/a.jpg"], row["image_urls"])
        self.assertEqual("LED Lights", row["category"])
        self.assertIn("bsr", row["missing_fields"])

    def test_known_product_aliases_preserve_bsr_and_all_images(self):
        row = normalize_product_detail(result({
            "asin": "B000000001", "brand_name": "Brand", "product_title": "Title",
            "images": [{"url": "https://img.example/a.jpg"}, {"imageUrl": "https://img.example/b.jpg"}],
            "selling_price": 9.99, "rating": 4.5, "ratings": 12, "monthly_sales": 30,
            "category_name": "LED Lights", "salesRank": 37,
            "variations": [{"size": "100ft"}], "bullets": ["Dimmable", "Easy install"],
        }), asin="B000000001", marketplace="US")
        self.assertEqual(37, row["bsr"])
        self.assertEqual(["https://img.example/a.jpg", "https://img.example/b.jpg"], row["image_urls"])
        self.assertEqual(1, row["variation_count"])
        self.assertNotIn("bsr", row["missing_fields"])

    def test_error_envelope_is_rejected_even_when_data_exists(self):
        with self.assertRaises(ValueError):
            normalize_product_detail({"content": [{"type": "text", "text": json.dumps({"code": 500, "data": {"asin": "B000000001", "title": "bad"}})}]}, asin="B000000001", marketplace="US")

    def test_provider_gallery_replaces_stale_single_image(self):
        fake = FakeTransport()
        adapter = SorftimeCatalogAdapter(transport=fake, marketplace="US", budget=SorftimeCallBudget(1), max_calls=1)
        enriched = adapter.enrich_profile({"self_asin": "B000000001", "competitors": [], "self_product": {"asin": "B000000001", "image_urls": ["https://img.example/old.jpg"]}})
        self.assertEqual(["https://img.example/a.jpg"], enriched["self_product"]["image_urls"])

    def test_percent_strings_are_normalized(self):
        payload = result({"sample_stats": "top 20", "analysis_results": [{"product_feature": "调光", "product_count_share": "64.2% (5/19)", "monthly_sales_share": "28.47%", "feature_description": "x"}]})
        features = normalize_category_feature_response(payload)
        self.assertEqual(64.2, features["features"][0]["product_count_share"])
        self.assertEqual(28.47, features["features"][0]["monthly_sales_share"])
        self.assertAlmostEqual(0.642, features["features"][0]["product_count_share_ratio"])
        self.assertAlmostEqual(0.2847, features["features"][0]["monthly_sales_share_ratio"])

    def test_shared_budget_limits_profile_calls(self):
        fake = FakeTransport()
        adapter = SorftimeCatalogAdapter(transport=fake, marketplace="US", budget=SorftimeCallBudget(1), max_calls=1)
        profile = {"self_asin": "B000000001", "competitors": [{"asin": "B000000002"}], "self_product": None}
        result_profile = adapter.enrich_profile(profile)
        self.assertEqual(1, len(fake.calls))
        self.assertEqual(1, result_profile["provider_calls"])
        self.assertEqual(1, result_profile["competitors"][0].get("asin") == "B000000002")

    def test_primary_keyword_fetches_one_normalized_category_snapshot(self):
        fake = FakeTransport()
        adapter = SorftimeCatalogAdapter(transport=fake, marketplace="US", budget=SorftimeCallBudget(2), max_calls=2)
        profile = {"self_asin": "B000000001", "primary_core_keyword": "led lights",
                   "core_keywords": ["led lights"], "competitors": [], "self_product": None}
        enriched = adapter.enrich_profile(profile)
        self.assertEqual(["product_detail", "similar_product_feature"], [name for name, _ in fake.calls])
        self.assertEqual("led lights", adapter.last_category_features["primary_core_keyword"])
        self.assertEqual(1, len(adapter.last_category_features["features"]))
        self.assertEqual(2, enriched["provider_calls"])


if __name__ == "__main__":
    unittest.main()
