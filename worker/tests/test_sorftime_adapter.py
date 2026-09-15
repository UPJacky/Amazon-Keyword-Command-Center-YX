import json
import re
import tempfile
import unittest

from worker.competitors.category_features import normalize_category_features
from worker.providers.base import ProviderAttemptBudget, RetryPolicy
from worker.providers.cache import ProviderCache
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
    def test_shared_total_attempt_budget_blocks_before_second_provider_request(self):
        total = ProviderAttemptBudget(1)
        first_transport = FakeTransport()
        first = SorftimeCatalogAdapter(
            transport=first_transport, marketplace="US", max_calls=1,
            budget=SorftimeCallBudget(1), attempt_budget=total)
        first.fetch_product("B000000001")
        self.assertEqual(1, total.used_attempts)

        second_transport = FakeTransport()
        second = SorftimeCatalogAdapter(
            transport=second_transport, marketplace="US", max_calls=1,
            budget=SorftimeCallBudget(1), attempt_budget=total)
        with self.assertRaisesRegex(RuntimeError, "TOTAL_PROVIDER_ATTEMPTS_EXHAUSTED"):
            second.fetch_product("B000000002")
        self.assertEqual([], second_transport.calls)

    def test_gallery_provenance_missing_fields_and_call_delta(self):
        adapter = SorftimeCatalogAdapter(transport=FakeTransport(), marketplace="US", max_calls=3)
        profile = {"self_asin": "B000000001", "competitors": [], "self_product": {
            "main_image_url": "https://img.example/old.jpg", "source": "old",
            "sampled_at": "2020-01-01", "missing_fields": ["title"]}}
        first = adapter.enrich_profile(profile)
        row = first["self_product"]
        self.assertNotIn("title", row["missing_fields"])
        self.assertEqual("2020-01-01", row["field_provenance"]["main_image_url"]["previous"]["sampled_at"])
        self.assertNotEqual("2020-01-01", row["field_provenance"]["image_urls"]["selected"]["sampled_at"])
        self.assertTrue(row["gallery"][0]["source_image_id"])
        receipt = first["provider_usage"]["call_receipts"][0]
        self.assertRegex(receipt["request_sha256"], r"^[a-f0-9]{64}$")
        self.assertRegex(receipt["response_sha256"], r"^[a-f0-9]{64}$")
        self.assertNotIn("B000000001", json.dumps(receipt))
        second = adapter.enrich_profile(first)
        self.assertEqual(2, second["provider_calls"])

    def test_budget_and_no_result_have_explicit_outcomes(self):
        class Empty:
            def call(self, name, arguments):
                return result({})
        adapter = SorftimeCatalogAdapter(transport=Empty(), marketplace="US", max_calls=1)
        enriched = adapter.enrich_profile({"self_asin": "B000000001", "competitors": [{"asin": "B000000002"}]})
        self.assertEqual(["no_result", "budget_exhausted"], [x["status"] for x in enriched["provider_outcomes"]])
        self.assertEqual(1, enriched["provider_calls"])

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

    def test_product_text_and_category_aliases_are_retained_for_evidence(self):
        row = normalize_product_detail(result({
            "asin": "B000000001", "title": "Dimmable LED lights",
            "bullets": ["Color adjustable"], "attributes": {"Control": "App"},
            "description": "Use in bedroom scenes.",
        }), asin="B000000001", marketplace="US")
        self.assertEqual(["Color adjustable"], row["bullet_points"])
        self.assertEqual({"Control": "App"}, row["attributes"])
        self.assertEqual("Use in bedroom scenes.", row["description"])
        features = normalize_category_feature_response(result({
            "analysis_results": [{"product_feature": "调光", "english_name": "dimmable",
                                   "keywords": ["color adjustable"], "feature_description": "x"}]
        }))
        self.assertEqual("dimmable", features["features"][0]["english_name"])
        self.assertEqual(["color adjustable"], features["features"][0]["keywords"])

    def test_new_provider_text_replaces_stale_snapshot_text(self):
        class TextTransport:
            def call(self, name, arguments):
                return result({"asin": arguments["asin"], "title": "New title",
                               "bullets": ["New bullet"], "attributes": {"Control": "App"}})

        adapter = SorftimeCatalogAdapter(transport=TextTransport(), marketplace="US", max_calls=1)
        profile = adapter.enrich_profile({
            "self_asin": "B000000001", "competitors": [],
            "self_product": {"asin": "B000000001", "title": "Old title", "bullet_points": ["Old bullet"]},
        })
        self.assertEqual("New title", profile["self_product"]["title"])
        self.assertEqual(["New bullet"], profile["self_product"]["bullet_points"])
        self.assertEqual({"Control": "App"}, profile["self_product"]["attributes"])

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

    def test_disk_cache_reuses_product_and_feature_facts_across_adapters(self):
        with tempfile.TemporaryDirectory() as directory:
            cache = ProviderCache(directory, ttl_seconds=3600)
            first_transport = FakeTransport()
            first = SorftimeCatalogAdapter(transport=first_transport, marketplace="US", max_calls=2,
                                            budget=SorftimeCallBudget(2), cache=cache, cache_namespace="test")
            profile = {"self_asin": "B000000001", "primary_core_keyword": "led lights",
                       "core_keywords": ["led lights"], "competitors": [], "self_product": None}
            first.enrich_profile(profile)
            self.assertEqual(2, len(first_transport.calls))
            second_transport = FakeTransport()
            second = SorftimeCatalogAdapter(transport=second_transport, marketplace="US", max_calls=2,
                                             budget=SorftimeCallBudget(2), cache=cache, cache_namespace="test")
            result_profile = second.enrich_profile(profile)
            self.assertEqual([], second_transport.calls)
            self.assertEqual(2, result_profile["provider_usage"]["cache_hits"])
            self.assertEqual(0, result_profile["provider_usage"]["actual_calls"])

    def test_production_preflight_blocks_partial_profile_when_budget_is_short(self):
        fake = FakeTransport()
        adapter = SorftimeCatalogAdapter(
            transport=fake, marketplace="US", max_calls=3,
            budget=SorftimeCallBudget(2), preflight_whole_task=True,
        )
        profile = {
            "self_asin": "B000000001", "competitors": [{"asin": "B000000002"}],
            "primary_core_keyword": "led lights", "self_product": None,
        }
        enriched = adapter.enrich_profile(profile)
        self.assertEqual(3, adapter.estimate_required_calls(profile))
        self.assertEqual([], fake.calls)
        self.assertEqual(0, enriched["provider_usage"]["actual_calls"])
        self.assertEqual(3, enriched["provider_usage"]["estimated_calls"])
        self.assertEqual(
            ["budget_exhausted", "budget_exhausted"],
            [item["status"] for item in enriched["provider_outcomes"]],
        )
        self.assertEqual("budget_exhausted", enriched["category_features_error"])

    def test_production_preflight_allows_fully_cached_profile_with_zero_calls(self):
        with tempfile.TemporaryDirectory() as directory:
            cache = ProviderCache(directory, ttl_seconds=3600)
            profile = {
                "self_asin": "B000000001", "primary_core_keyword": "led lights",
                "core_keywords": ["led lights"], "competitors": [], "self_product": None,
            }
            first = SorftimeCatalogAdapter(
                transport=FakeTransport(), marketplace="US", max_calls=2,
                budget=SorftimeCallBudget(2), cache=cache, cache_namespace="preflight",
                preflight_whole_task=True,
            )
            first.enrich_profile(profile)
            second_transport = FakeTransport()
            second = SorftimeCatalogAdapter(
                transport=second_transport, marketplace="US", max_calls=2,
                budget=SorftimeCallBudget(1), cache=cache, cache_namespace="preflight",
                preflight_whole_task=True,
            )
            enriched = second.enrich_profile(profile)
            self.assertEqual(0, second.estimate_required_calls(profile))
            self.assertEqual([], second_transport.calls)
            self.assertEqual(0, enriched["provider_usage"]["actual_calls"])
            self.assertEqual(0, enriched["provider_usage"]["estimated_calls"])
            self.assertEqual(2, enriched["provider_usage"]["cache_hits"])

    def test_retryable_5xx_is_bounded_and_consumes_budget(self):
        class Flaky:
            def __init__(self):
                self.calls = 0

            def call(self, name, arguments):
                self.calls += 1
                if self.calls == 1:
                    return {"status": 503}
                return result({"asin": arguments["asin"], "title": "Title"})

        sleeps = []
        transport = Flaky()
        adapter = SorftimeCatalogAdapter(transport=transport, marketplace="US", max_calls=2,
                                         budget=SorftimeCallBudget(2),
                                         retry_policy=RetryPolicy(max_retries=1, backoff_seconds=(0,)),
                                         sleep_fn=sleeps.append)
        row = adapter.fetch_product("B000000001")
        self.assertEqual("Title", row["title"])
        self.assertEqual(2, transport.calls)
        self.assertEqual(1, adapter.retries)
        self.assertEqual([0], sleeps)


if __name__ == "__main__":
    unittest.main()
