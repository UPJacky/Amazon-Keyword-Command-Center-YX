"""Offline recorded-contract tests; all transport attempts are fake."""

import copy
import io
import json
import re
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import Mock, patch

from worker.pipeline.task_runner import _provider_result, run_task
from worker.providers.market_merge import MARKET_FIELDS, merge_market_data
from worker.providers.mcp_http_transport import McpHttpTransport
from worker.providers.orchestrator import ProviderBatchError
from worker.providers.base import ProviderAttemptBudget, RetryPolicy
from worker.providers.cache import ProviderCache
from worker.providers.xiyou_live_enrichment import XiyouCallBudget, XiyouLiveEnricher


ASIN = "B012345678"
FIXTURE = Path(__file__).resolve().parents[2] / "data/fixtures/商品推广_搜索词_报告_LED演示.xlsx"


def parsed(*keywords):
    return {"aggregated_rows": [{"keyword": word} for word in keywords]}


def record(keyword="led light", **changes):
    # Synthetic values of observed types, not claims about the live sample.
    return {"searchTerm": keyword, "competitiveDifficulty": 37,
            "clickConversionRate": "12.5", "organicRotation": "unknown",
            "costPerClick": {"value": "1.25", "minSuggestedBid": "0.80", "maxSuggestedBid": "1.70"},
            "abaReport": {"reportFromDate": "2026-08-23", "reportToDate": "2026-08-29",
                          "weeklySearchVolume": 1200, "searchFrequencyRank": 42,
                          "topAsins": [{"unconfirmed_item_schema": True}] * 3}, **changes}


def response(*entries, cost=1, status=200):
    return {"jsonrpc": "2.0", "id": 1, "result": {
        "content": [{"type": "text", "text": "Ignored; structuredContent is authoritative"}],
        "structuredContent": {"status": status, "cost_credits": cost,
                              "data": {"list": list(entries), "total": len(entries)}}}}


class XiyouLiveEnrichmentTests(unittest.TestCase):
    def setUp(self):
        # Real sockets are forbidden even if the implementation accidentally
        # starts a network path. McpHttpTransport tests inject a fake opener.
        self.no_network = patch("socket.socket.connect", side_effect=AssertionError("network forbidden"))
        self.no_network.start()
        self.addCleanup(self.no_network.stop)

    def make(self, payload=None, *, budget=None, max_keywords=10, country="US", asin=ASIN):
        transport = Mock()
        transport.call.return_value = payload if payload is not None else response(record())
        budget = budget if budget is not None else XiyouCallBudget(3, 3)
        enricher = XiyouLiveEnricher(transport=transport, country=country, asin=asin,
                                   max_keywords=max_keywords, budget=budget)
        return enricher, transport, budget

    def test_recorded_contract_and_strict_pipeline_shape(self):
        enrich, transport, budget = self.make()
        source, config = parsed("led light"), {"unchanged": True}
        original = copy.deepcopy((source, config))
        result = enrich(source, config)
        self.assertEqual({"market_rows", "provider_snapshot_version", "usage", "provider_usage"}, set(result))
        _provider_result(result)
        row = result["market_rows"][0]
        self.assertEqual(37, row["competitive_difficulty"])
        self.assertEqual(1200, row["weekly_search_volume"])
        self.assertEqual(42, row["aba_search_frequency_rank"])
        self.assertEqual("2026-08-23", row["aba_report_from_date"])
        self.assertEqual("2026-08-29", row["aba_report_to_date"])
        self.assertIsNone(row["market_search_volume"])
        self.assertEqual(1200, row["provider_observations"]["abaReport"]["weeklySearchVolume"])
        self.assertEqual("2026-08-23", row["provider_observations"]["abaReport"]["reportFromDate"])
        self.assertFalse(row["full_report_complete"])
        self.assertFalse(enrich.full_report_complete)
        self.assertFalse(enrich.real_provider_verified,
                         "injected Mock transport must not inherit live provenance")
        self.assertEqual(original, (source, config))
        transport.call.assert_called_once_with("get_keyword_info", {"keywords": ["led light"], "country": "US"})
        self.assertEqual(1, budget.used_calls)
        self.assertEqual(1, budget.used_credits)
        receipt = result["provider_usage"]["xiyou"]["call_receipts"][0]
        self.assertRegex(receipt["request_sha256"], r"^[a-f0-9]{64}$")
        self.assertRegex(receipt["response_sha256"], r"^[a-f0-9]{64}$")
        self.assertNotIn("led light", json.dumps(receipt))

    def test_shared_total_attempt_budget_counts_retries_and_is_persisted(self):
        total = ProviderAttemptBudget(2)
        transport = Mock()
        transport.call.side_effect = [
            {"status": 503},
            response(record()),
        ]
        enricher = XiyouLiveEnricher(
            transport=transport, country="US", asin=ASIN, max_keywords=1,
            budget=XiyouCallBudget(2, 2), attempt_budget=total,
            retry_policy=RetryPolicy(max_retries=1, backoff_seconds=()),
        )
        result = enricher(parsed("led light"), {})
        self.assertEqual(2, total.used_attempts)
        self.assertEqual({"provider": "aggregate", "actual_calls": 2,
                          "max_attempts": 2, "outcome": "bounded"},
                         result["provider_usage"]["total_provider_attempts"])
        self.assertEqual(2, len(transport.call.call_args_list))

        blocked_transport = Mock()
        blocked = XiyouLiveEnricher(
            transport=blocked_transport, country="US", asin=ASIN, max_keywords=1,
            budget=XiyouCallBudget(1, 1), attempt_budget=total,
        )
        with self.assertRaises(ProviderBatchError) as caught:
            blocked(parsed("another term"), {})
        self.assertEqual("TOTAL_PROVIDER_ATTEMPTS_EXHAUSTED", caught.exception.code)
        blocked_transport.call.assert_not_called()

    def test_live_provenance_is_explicit_instance_metadata(self):
        enrich, transport, _ = self.make()
        self.assertFalse(enrich.real_provider_verified)
        trusted = XiyouLiveEnricher(transport=transport, country="US", asin=ASIN,
                                    max_keywords=1, budget=XiyouCallBudget(1, 1),
                                    real_provider_verified=True)
        self.assertTrue(trusted.real_provider_verified)

    def test_explicit_cache_reuses_successful_result_across_enricher_instances(self):
        with tempfile.TemporaryDirectory() as directory:
            cache = ProviderCache(Path(directory), ttl_seconds=3600)
            first_transport = Mock()
            first_transport.call.return_value = response(record())
            first = XiyouLiveEnricher(transport=first_transport, country="US", asin=ASIN,
                                      max_keywords=1, budget=XiyouCallBudget(1, 1),
                                      cache=cache, cache_namespace="test")
            first_result = first(parsed("led light"), {})
            second_transport = Mock(side_effect=AssertionError("cache miss would call Provider"))
            second = XiyouLiveEnricher(transport=second_transport, country="US", asin=ASIN,
                                       max_keywords=1, budget=XiyouCallBudget(1, 1),
                                       cache=cache, cache_namespace="test")
            second_result = second(parsed("led light"), {})
            self.assertEqual(first_result["provider_snapshot_version"], second_result["provider_snapshot_version"])
            self.assertEqual(1, second_result["usage"]["cache_hits"])
            self.assertEqual(0, second_result["usage"]["actual_calls"])
            second_transport.call.assert_not_called()

    def test_optional_competitor_snapshot_projects_asins_and_images(self):
        transport = Mock()
        keyword_payload = response(record())
        competitor_payload = response(
            {"asin": ASIN, "country": "US", "asinInfo": {
                "title": "Own product", "picUrl": "https://img.example/self.jpg",
                "price": 9.99, "currency": "USD", "stars": 4.4, "ratings": 100,
            }, "trafficSummary": {}, "ranks": []},
            {"asin": "B098765432", "country": "US", "asinInfo": {
                "title": "Competitor one", "picUrl": "https://img.example/one.jpg",
                "price": 12.99, "currency": "USD", "stars": 4.5, "ratings": 200,
            }, "trafficSummary": {}, "ranks": []},
            {"asin": "B087654321", "country": "US", "asinInfo": {
                "title": "Competitor two", "picUrl": "https://img.example/two.jpg",
                "price": 11.99, "currency": "USD", "stars": 4.3, "ratings": 150,
            }, "trafficSummary": {}, "ranks": []},
            {"asin": "B076543210", "country": "US", "asinInfo": {
                "title": "Competitor three", "picUrl": "https://img.example/three.jpg",
                "price": 10.99, "currency": "USD", "stars": 4.2, "ratings": 90,
            }, "trafficSummary": {}, "ranks": []},
        )
        transport.call.side_effect = [keyword_payload, competitor_payload]
        budget = XiyouCallBudget(3, 3)
        enrich = XiyouLiveEnricher(transport=transport, country="US", asin=ASIN,
                                    max_keywords=10, budget=budget,
                                    enable_competitors=True)
        result = enrich(parsed("led light"), {})
        self.assertEqual(2, result["usage"]["actual_calls"])
        self.assertEqual(2, budget.used_credits)
        profile = result["competitor_profile"]
        self.assertEqual(3, len(profile["competitors"]))
        self.assertEqual(ASIN, profile["self_product"]["asin"])
        self.assertEqual("https://img.example/one.jpg", profile["competitors"][0]["image_urls"][0])
        self.assertEqual("get_keyword_asin_analysis", transport.call.call_args_list[1].args[0])

    def test_explicit_competitor_ranks_feed_only_the_sampled_keyword(self):
        transport = Mock()
        transport.call.side_effect = [response(record()), response(
            {"asin": ASIN, "asinInfo": {"title": "Own"},
             "ranks": [{"positionCode": "or", "totalRank": 8}]},
            {"asin": "B098765432", "asinInfo": {"title": "One"},
             "ranks": [{"positionCode": "or", "totalRank": 2}]},
            {"asin": "B087654321", "asinInfo": {"title": "Two"},
             "ranks": [{"positionCode": "or", "totalRank": 4}]},
            {"asin": "B076543210", "asinInfo": {"title": "Three"},
             "ranks": [{"positionCode": "or", "totalRank": 6}]},
        )]
        enrich = XiyouLiveEnricher(transport=transport, country="US", asin=ASIN,
                                   max_keywords=2, budget=XiyouCallBudget(2, 2),
                                   enable_competitors=True)
        result = enrich(parsed("led light", "room decor"), {})
        led = next(row for row in result["market_rows"] if row["keyword"] == "led light")
        other = next(row for row in result["market_rows"] if row["keyword"] == "room decor")
        self.assertEqual(8, led["organic_rank"])
        self.assertEqual([2, 4, 6], [item["organic_rank"] for item in led["benchmark_asins"]])
        self.assertIsNone(other["organic_rank"])
        self.assertEqual("led light", led["provider_observations"]["rankSnapshot"]["keyword"])

    def test_category_features_produce_auditable_checklist_and_text_evidence(self):
        transport = Mock()
        transport.call.side_effect = [response(record()), response(
            {"asin": ASIN, "asinInfo": {"title": "Own LED lights", "picUrl": "https://img/self.jpg"}},
            {"asin": "B098765432", "asinInfo": {"title": "Competitor dimmable lights", "picUrl": "https://img/one.jpg"},
             "trafficSummary": {}, "ranks": []})]
        class Catalog:
            last_category_features = {"features": [{"feature_id": "f1", "name": "dimmable", "source_refs": ["category:1"]}],
                                       "source_refs": ["category:1"]}
            def enrich_profile(self, profile):
                return profile
        enrich = XiyouLiveEnricher(transport=transport, country="US", asin=ASIN,
                                   max_keywords=1, budget=XiyouCallBudget(2, 2),
                                   enable_competitors=True, catalog_adapter=Catalog())
        result = enrich(parsed("led light"), {})
        self.assertEqual("draft", result["buyer_checklist"]["status"])
        self.assertEqual(1, len(result["buyer_checklist"]["items"]))
        self.assertEqual("draft", result["text_evidence"]["status"])
        self.assertEqual(2, len(result["text_evidence"]["cells"]))

    def test_visual_adapter_is_called_only_with_catalog_scope_and_usage_is_persisted(self):
        transport = Mock()
        transport.call.side_effect = [response(record()), response(
            {"asin": ASIN, "asinInfo": {"title": "Own LED lights", "picUrl": "https://img/self.jpg"}},
            {"asin": "B098765432", "asinInfo": {"title": "Competitor dimmable lights", "picUrl": "https://img/one.jpg"},
             "trafficSummary": {}, "ranks": []})]
        class Catalog:
            last_category_features = {"features": [{"feature_id": "f1", "name": "dimmable", "source_refs": ["category:1"]}],
                                       "source_refs": ["category:1"]}
            def enrich_profile(self, profile):
                return profile
        class Visual:
            def __init__(self):
                self.calls = []
            def enrich(self, **kwargs):
                self.calls.append(kwargs)
                return {"visual_evidence": {"evidence_version": "visual-v1", "expected_element_ids": ["f1"], "observations": []},
                        "provider_usage": {"actual_calls": 1, "cache_hits": 0, "output_tokens": 3, "failures": 0}}
        visual = Visual()
        enrich = XiyouLiveEnricher(transport=transport, country="US", asin=ASIN,
                                   max_keywords=1, budget=XiyouCallBudget(2, 2),
                                   enable_competitors=True, catalog_adapter=Catalog(),
                                   visual_adapter=visual)
        result = enrich(parsed("led light"), {})
        self.assertEqual(1, len(visual.calls))
        self.assertEqual(["f1"], [item["feature_id"] for item in visual.calls[0]["expected_elements"]])
        self.assertIn("visual_evidence", result)
        self.assertEqual(3, result["provider_usage"]["doubao"]["output_tokens"])

    def test_unknown_fields_do_not_gain_invented_units_ranks_or_shares(self):
        raw = record(ranks=[{"positionCode": "or", "totalRank": 1}],
                     suggested_bid=1.2, market_opportunity_score=99, organic_rank=1)
        enrich, _, _ = self.make(response(raw))
        row = enrich(parsed("led light"), {"currency_code": "USD"})["market_rows"][0]
        confirmed = {"competitive_difficulty", "weekly_search_volume", "aba_search_frequency_rank",
                     "aba_report_from_date", "aba_report_to_date"}
        missing = MARKET_FIELDS - confirmed
        for field in missing:
            self.assertIsNone(row[field], field)
        self.assertEqual(sorted(missing), row["missing_fields"])
        self.assertNotIn("costPerClick", row["provider_observations"])

    def test_nulls_and_absent_records_remain_missing(self):
        enrich, _, _ = self.make(response(record(competitiveDifficulty=None, abaReport=None, costPerClick=None)))
        rows = enrich(parsed("led light", "absent"), {})["market_rows"]
        for row in rows:
            self.assertEqual(sorted(MARKET_FIELDS), row["missing_fields"])
            self.assertTrue(all(row[field] is None for field in MARKET_FIELDS))
        self.assertIsNone(rows[1]["provider_observations"])

    def test_zero_confirmed_values_are_preserved(self):
        raw = record(competitiveDifficulty=0)
        raw["abaReport"]["weeklySearchVolume"] = 0
        enrich, _, _ = self.make(response(raw))
        row = enrich(parsed("led light"), {})["market_rows"][0]
        self.assertEqual(0, row["competitive_difficulty"])
        self.assertEqual(0, row["weekly_search_volume"])
        self.assertEqual(0, row["provider_observations"]["abaReport"]["weeklySearchVolume"])
        self.assertNotIn("competitive_difficulty", row["missing_fields"])
        self.assertNotIn("weekly_search_volume", row["missing_fields"])

    def test_deduplication_cap_and_exact_join_spelling(self):
        enrich, transport, _ = self.make(max_keywords=1)
        words = ["LED Light", " led  light ", "LED Light", "unselected"]
        result = enrich(parsed(*words), {})
        transport.call.assert_called_once_with("get_keyword_info", {"keywords": ["LED Light"], "country": "US"})
        self.assertEqual(2, result["usage"]["duplicates_suppressed"])
        self.assertEqual(4, result["usage"]["requested_keywords"])
        merged = merge_market_data([{"keyword": word, "spend": 19} for word in words], result["market_rows"])
        self.assertEqual([37, 37, 37, None], [row["competitive_difficulty"] for row in merged])
        self.assertTrue(all(row["spend"] == 19 for row in merged))
        self.assertFalse(result["market_rows"][-1]["provider_sampled"])

    def test_cross_keyword_duplicate_and_cross_identity_responses_rejected(self):
        cases = [response(record("other")), response(record(), record()),
                 response(record(country="GB")), response(record(asin="B087654321")),
                 response(record("unselected"))]
        for payload in cases:
            with self.subTest(payload=payload):
                enrich, _, _ = self.make(payload, max_keywords=1)
                with self.assertRaises(ProviderBatchError) as caught:
                    enrich(parsed("led light", "unselected"), {})
                self.assertEqual("INVALID_KEYWORD_RESPONSE", caught.exception.code)

    def test_empty_list_does_not_fabricate_metrics(self):
        enrich, _, budget = self.make(response())
        row = enrich(parsed("led light"), {})["market_rows"][0]
        self.assertEqual(sorted(MARKET_FIELDS), row["missing_fields"])
        self.assertEqual(1, budget.used_credits)

    def test_no_keywords_means_zero_calls_even_with_zero_budget(self):
        enrich, transport, budget = self.make(budget=XiyouCallBudget(0, 0))
        result = enrich(parsed(), {})
        _provider_result(result)
        self.assertEqual([], result["market_rows"])
        self.assertEqual(0, result["usage"]["actual_calls"])
        self.assertEqual(0, budget.used_credits)
        transport.call.assert_not_called()

    def test_one_request_is_capped_at_ten_keywords(self):
        words = [f"word {i}" for i in range(10)]
        enrich, transport, budget = self.make(response(*(record(word) for word in words)),
                                             max_keywords=10, budget=XiyouCallBudget(1, 1))
        result = enrich(parsed(*words), {})
        self.assertEqual(10, len(result["market_rows"]))
        self.assertEqual(1, transport.call.call_count)
        self.assertEqual(1, budget.used_credits)

    def test_confirmed_primary_keyword_is_first_query_term_even_if_report_order_differs(self):
        enrich, transport, _ = self.make(response(record("primary term"), record("ad term")), max_keywords=2)
        enrich = XiyouLiveEnricher(transport=transport, country="US", asin=ASIN, max_keywords=2,
                                   budget=XiyouCallBudget(1, 1), primary_core_keyword="primary term",
                                   core_keywords=["primary term"])
        enrich(parsed("ad term", "primary term"), {})
        self.assertEqual(["primary term", "ad term"], transport.call.call_args.args[1]["keywords"])

    def test_requested_core_term_absent_from_ads_survives_provider_and_merge(self):
        _, transport, _ = self.make(response(record("primary term"), record("ad term")))
        enrich = XiyouLiveEnricher(transport=transport, country="US", asin=ASIN,
            max_keywords=2, budget=XiyouCallBudget(1, 1), primary_core_keyword="primary term")
        result = enrich(parsed("ad term"), {})
        self.assertEqual({"primary term", "ad term"}, {r["keyword"] for r in result["market_rows"]})
        merged = merge_market_data([{"keyword": "ad term", "spend": 5}], result["market_rows"])
        primary = next(row for row in merged if row["keyword"] == "primary term")
        self.assertTrue(primary["provider_only"])
        self.assertEqual(1200, primary["weekly_search_volume"])
        self.assertIsNone(primary.get("spend"))
        self.assertEqual(5, sum(row.get("spend") or 0 for row in merged))

    def test_requested_competitors_are_selected_and_missing_are_traceable(self):
        transport = Mock()
        transport.call.side_effect = [response(record()), response(
            {"asin": ASIN, "asinInfo": {"title": "Own", "picUrl": "https://img/self.jpg"}},
            {"asin": "B098765432", "asinInfo": {"title": "Requested", "picUrl": "https://img/requested.jpg"}},
            {"asin": "B087654321", "asinInfo": {"title": "Other", "picUrl": "https://img/other.jpg"}},
        )]
        enrich = XiyouLiveEnricher(transport=transport, country="US", asin=ASIN, max_keywords=1,
                                   budget=XiyouCallBudget(3, 3), enable_competitors=True,
                                   competitor_asins=["B087654321", "B076543210"])
        result = enrich(parsed("led light"), {})
        profile = result["competitor_profile"]
        self.assertEqual(["B087654321"], [row["asin"] for row in profile["competitors"]])
        self.assertEqual(["B076543210"], profile["missing_competitor_asins"])

    def test_call_and_credit_preflight_reject_without_transport(self):
        for calls, credits, count in [(0, 2, 1), (2, 0, 1)]:
            with self.subTest(calls=calls, credits=credits, count=count):
                enrich, transport, budget = self.make(max_keywords=10, budget=XiyouCallBudget(calls, credits))
                with self.assertRaises(ProviderBatchError):
                    enrich(parsed(*(f"word {i}" for i in range(count))), {})
                self.assertEqual(0, budget.used_calls)
                self.assertEqual(0, budget.used_credits)
                transport.call.assert_not_called()

    def test_production_preflight_rejects_partial_keyword_and_competitor_task(self):
        transport = Mock()
        enrich = XiyouLiveEnricher(
            transport=transport, country="US", asin=ASIN, max_keywords=1,
            budget=XiyouCallBudget(1, 1), enable_competitors=True,
            preflight_whole_task=True,
        )
        with self.assertRaises(ProviderBatchError) as caught:
            enrich(parsed("led light"), {})
        self.assertEqual("CALL_BUDGET_EXHAUSTED", caught.exception.code)
        self.assertEqual(2, caught.exception.usage["estimated_calls"])
        self.assertEqual(0, enrich._budget.used_calls)
        self.assertEqual(0, enrich._budget.used_credits)
        transport.call.assert_not_called()

    def test_production_preflight_allows_cached_whole_task_with_zero_calls(self):
        with tempfile.TemporaryDirectory() as directory:
            cache = ProviderCache(Path(directory), ttl_seconds=3600)
            first_transport = Mock()
            first_transport.call.side_effect = [
                response(record()),
                response(
                    {"asin": ASIN, "asinInfo": {"title": "Own", "picUrl": "https://img/self.jpg"}},
                    {"asin": "B098765432", "asinInfo": {"title": "Other", "picUrl": "https://img/other.jpg"}},
                ),
            ]
            first = XiyouLiveEnricher(
                transport=first_transport, country="US", asin=ASIN, max_keywords=1,
                budget=XiyouCallBudget(2, 2), enable_competitors=True,
                cache=cache, cache_namespace="production", preflight_whole_task=True,
            )
            first(parsed("led light"), {})
            second_transport = Mock(side_effect=AssertionError("cached task must not call Provider"))
            second = XiyouLiveEnricher(
                transport=second_transport, country="US", asin=ASIN, max_keywords=1,
                budget=XiyouCallBudget(0, 0), enable_competitors=True,
                cache=cache, cache_namespace="production", preflight_whole_task=True,
            )
            result = second(parsed("led light"), {})
            self.assertEqual(0, result["usage"]["estimated_calls"])
            self.assertEqual(0, result["usage"]["actual_calls"])
            self.assertEqual(1, result["usage"]["cache_hits"])
            second_transport.call.assert_not_called()

    def test_shared_budget_survives_factory_recreation_and_concurrency(self):
        budget = XiyouCallBudget(1, 1)
        first, transport_a, _ = self.make(budget=budget)
        second, transport_b, _ = self.make(budget=budget)
        def run(enrich):
            try:
                enrich(parsed("led light"), {})
                return "passed"
            except ProviderBatchError:
                return "blocked"
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(run, [first, second]))
        self.assertCountEqual(["passed", "blocked"], results)
        self.assertEqual(1, transport_a.call.call_count + transport_b.call.call_count)
        self.assertEqual(1, budget.used_calls)

    def test_missing_invalid_cost_poison_shared_budget(self):
        for cost in (None, -1, True, "1", 1.0, float("nan"), float("inf")):
            with self.subTest(cost=cost):
                enrich, transport, budget = self.make(response(record(), cost=cost))
                with self.assertRaises(ProviderBatchError) as caught:
                    enrich(parsed("led light"), {})
                self.assertEqual("INVALID_COST_CREDITS", caught.exception.code)
                self.assertTrue(budget.blocked)
                self.assertEqual(1, budget.used_credits)
                another, other_transport, _ = self.make(budget=budget)
                with self.assertRaises(ProviderBatchError):
                    another(parsed("led light"), {})
                other_transport.call.assert_not_called()
                self.assertEqual(1, transport.call.call_count)

    def test_overcharge_is_recorded_unclamped_and_blocks_further_calls(self):
        enrich, _, budget = self.make(response(record(), cost=9), budget=XiyouCallBudget(10, 2))
        with self.assertRaises(ProviderBatchError) as caught:
            enrich(parsed("led light"), {})
        self.assertEqual("COST_EXCEEDS_RESERVATION", caught.exception.code)
        self.assertEqual(9, budget.snapshot()["reported_credits"])
        self.assertEqual(9, budget.used_credits)
        self.assertTrue(budget.blocked)

    def test_low_cost_does_not_refund_conservative_reservation(self):
        enrich, _, budget = self.make(response(record(), cost=0))
        enrich(parsed("led light"), {})
        self.assertEqual(1, budget.used_credits)
        self.assertEqual(0, budget.snapshot()["reported_credits"])

    def test_business_error_status_is_not_success(self):
        for status in (None, True, "200", 201, 400, 429, 500):
            with self.subTest(status=status):
                enrich, transport, budget = self.make(response(record(), status=status))
                with self.assertRaises(ProviderBatchError) as caught:
                    enrich(parsed("led light"), {})
                self.assertEqual("BUSINESS_STATUS_FAILED", caught.exception.code)
                self.assertEqual(int(status == 429), caught.exception.usage["rate_limited"])
                self.assertEqual(1, budget.used_credits)
                self.assertEqual(1, transport.call.call_count)

    def test_explicit_retry_policy_retries_rate_limit_and_charges_each_attempt(self):
        transport = Mock()
        transport.call.side_effect = [response(record(), status=429), response(record())]
        sleeps = []
        budget = XiyouCallBudget(2, 2)
        enrich = XiyouLiveEnricher(transport=transport, country="US", asin=ASIN,
                                   max_keywords=1, budget=budget,
                                   retry_policy=RetryPolicy(max_retries=1, backoff_seconds=(0,)),
                                   sleep_fn=sleeps.append)
        result = enrich(parsed("led light"), {})
        self.assertEqual(2, transport.call.call_count)
        self.assertEqual(2, result["usage"]["actual_calls"])
        self.assertEqual(1, result["usage"]["retries"])
        self.assertEqual(1, result["usage"]["rate_limited"])
        self.assertEqual(2, budget.used_credits)
        self.assertEqual([0], sleeps)

    def test_transport_http_and_mcp_failures_never_retry_or_leak_details(self):
        cases = [{"status": 429}, {"status": 503}, {"jsonrpc": "2.0", "error": "PRIVATE"},
                 {"jsonrpc": "2.0", "result": {"isError": True, "content": "PRIVATE"}},
                 {"jsonrpc": "2.0", "result": {"content": [{"type": "text", "text": "PRIVATE"}]}},
                 {"result": response(record())["result"]}, []]
        for payload in cases:
            with self.subTest(payload=payload):
                enrich, transport, budget = self.make(payload)
                with self.assertRaises(ProviderBatchError) as caught:
                    enrich(parsed("led light"), {})
                self.assertNotIn("PRIVATE", str(caught.exception))
                self.assertTrue(budget.blocked)
                self.assertEqual(1, transport.call.call_count)
                self.assertEqual(0, caught.exception.usage["retries"])

    def test_transport_exception_consumes_attempt_and_blocks_unknown_charge(self):
        enrich, transport, budget = self.make()
        transport.call.side_effect = RuntimeError("PRIVATE_ENDPOINT_OR_TOKEN")
        with self.assertRaises(ProviderBatchError) as caught:
            enrich(parsed("led light"), {})
        self.assertNotIn("PRIVATE", str(caught.exception))
        self.assertEqual(1, caught.exception.usage["actual_calls"])
        self.assertEqual(1, budget.used_calls)
        self.assertTrue(budget.blocked)

    def test_invalid_shapes_totals_and_typed_metrics_fail_closed(self):
        entries = [record(competitiveDifficulty=True), record(competitiveDifficulty="37"),
                   record(competitiveDifficulty=-1), record(abaReport=[]),
                   record(abaReport={"weeklySearchVolume": "1200"}),
                   record(abaReport={"weeklySearchVolume": float("nan")}),
                   record(abaReport={"searchFrequencyRank": 0}),
                   record(abaReport={"reportFromDate": "2026-99-99"}),
                   record(abaReport={"reportFromDate": "2026-08-30", "reportToDate": "2026-08-29"})]
        payloads = [response(entry) for entry in entries]
        for data in (None, [], {"list": {}}, {"list": [], "total": True}, {"list": [], "total": 1}):
            payload = response()
            payload["result"]["structuredContent"]["data"] = data
            payloads.append(payload)
        for payload in payloads:
            with self.subTest(payload=payload):
                enrich, _, _ = self.make(payload)
                with self.assertRaises(ProviderBatchError):
                    enrich(parsed("led light"), {})

    def test_constructor_and_input_failures_do_not_call(self):
        for changes in ({"country": ""}, {"country": "us"}, {"country": None},
                        {"asin": ""}, {"asin": "bad"}, {"max_keywords": True},
                        {"max_keywords": 0}, {"max_keywords": 11}, {"max_keywords": float("inf")},
                        {"transport": None}, {"budget": None}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                XiyouLiveEnricher(**{**dict(transport=Mock(), country="US", asin=ASIN,
                                           max_keywords=10, budget=XiyouCallBudget(1, 1)), **changes})
        for value in (-1, True, None, float("inf"), "1"):
            with self.assertRaises(ValueError):
                XiyouCallBudget(value, 1)
            with self.assertRaises(ValueError):
                XiyouCallBudget(1, value)
        for source in ({}, {"aggregated_rows": None}, parsed(""), parsed(None), parsed("bad\nword"),
                       {"aggregated_rows": [None]}):
            enrich, transport, _ = self.make()
            with self.assertRaises(ProviderBatchError):
                enrich(source, {})
            transport.call.assert_not_called()

    def test_snapshot_stability_and_task_identity_partition(self):
        first, _, _ = self.make()
        version = first(parsed("led light"), {})["provider_snapshot_version"]
        self.assertEqual(version, first(parsed("led light"), {})["provider_snapshot_version"])
        for changes in ({"country": "GB"}, {"asin": "B087654321"},
                        {"payload": response(record(competitiveDifficulty=38))}):
            enrich, _, _ = self.make(**changes)
            self.assertNotEqual(version, enrich(parsed("led light"), {})["provider_snapshot_version"])

    def test_existing_mcp_http_transport_with_fake_opener(self):
        seen = []
        class FakeReply(io.BytesIO):
            headers = {"Content-Type": "application/json"}
        def opener(request, timeout):
            seen.append(json.loads(request.data))
            return FakeReply(json.dumps(response(record())).encode("utf-8"))
        transport = McpHttpTransport("https://offline.invalid/mcp", "FAKE_TEST_TOKEN", opener=opener)
        enrich = XiyouLiveEnricher(transport=transport, country="US", asin=ASIN,
                                   max_keywords=1, budget=XiyouCallBudget(1, 1))
        _provider_result(enrich(parsed("led light"), {}))
        self.assertEqual(1, len(seen))
        self.assertEqual("tools/call", seen[0]["method"])
        self.assertEqual("get_keyword_info", seen[0]["params"]["name"])
        self.assertEqual({"country", "keywords"}, set(seen[0]["params"]["arguments"]))

    def test_pipeline_integration_preserves_ad_facts_and_missingness(self):
        enrich, transport, _ = self.make(max_keywords=2)
        transport.call.side_effect = lambda tool, args: response(*(record(word) for word in args["keywords"]))
        with tempfile.TemporaryDirectory() as directory:
            result = run_task(FIXTURE, directory, "test-task", "test-run", provider_enricher=enrich)
            self.assertEqual("completed", result.status)
            report = json.loads(Path(result.report_path).read_text(encoding="utf-8"))
            root = Path(directory) / "test-task/test-run"
            source = json.loads((root / "ad-aggregated.json").read_text(encoding="utf-8"))
            originals = {row["keyword"]: row for row in source["aggregated_rows"]}
            for row in report["rows"]:
                for field in ("impressions", "clicks", "spend", "sales", "orders"):
                    self.assertEqual(originals[row["keyword"]][field], row[field])
                self.assertIn("organic_rank", row["missing_fields"])
                self.assertIn("suggested_bid", row["missing_fields"])
            self.assertEqual(2, sum(row["competitive_difficulty"] is not None for row in report["rows"]))
            receipt = json.loads((root / "provider-usage.json").read_text(encoding="utf-8"))
            self.assertEqual(report["provider_snapshot_version"], receipt["provider_snapshot_version"])
            self.assertEqual(1, receipt["usage"]["actual_calls"])

    def test_pipeline_rejects_bad_provider_response_without_formal_report(self):
        enrich, _, _ = self.make(response(record("NOT THE REQUESTED KEYWORD")), max_keywords=1)
        with tempfile.TemporaryDirectory() as directory:
            result = run_task(FIXTURE, directory, "test-task", "test-run", provider_enricher=enrich)
            self.assertEqual("provider", result.current_stage)
            self.assertEqual("failed", result.status)
            self.assertFalse(list((Path(directory) / "test-task/test-run").glob("report-*.json")))


if __name__ == "__main__":
    unittest.main()
