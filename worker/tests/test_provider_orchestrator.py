"""Executable fake-only examples for the production provider_enricher hook."""

import json
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from worker.providers.base import RetryPolicy
from worker.providers.cache import ProviderCache
from worker.providers.orchestrator import (
    CallBudget, ProviderBatchError, ProviderBatchOrchestrator, ProviderRequest,
)


class FakeTransport:
    def __init__(self, responses=None):
        self.calls = []
        self.responses = list(responses or [])
        self.lock = threading.Lock()

    def call(self, tool_name, arguments):
        with self.lock:
            self.calls.append((tool_name, arguments))
            response = self.responses.pop(0) if self.responses else {"keyword": "demo", "organic_rank": None}
        if isinstance(response, Exception):
            raise response
        return response


class ProviderOrchestratorTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.cache = ProviderCache(self.directory.name, ttl_seconds=10)
        self.transport = FakeTransport()
        self.request = ProviderRequest("fake.tool", {"keyword": "demo", "marketplace": "US"})

    def make(self, **overrides):
        options = dict(provider="fake", provider_version="schema-1", normalizer_version="normalizer-1",
                       cache_namespace="fake-dataset-1", cache=self.cache, normalize=lambda raw: raw,
                       transport=self.transport, budget=CallBudget(10), enabled=True,
                       sleep_fn=lambda _delay: None)
        options.update(overrides)
        return ProviderBatchOrchestrator(**options)

    def error(self, orchestrator, code, requests=None, **kwargs):
        with self.assertRaises(ProviderBatchError) as caught:
            orchestrator.run([self.request] if requests is None else requests, **kwargs)
        self.assertEqual(caught.exception.code, code)
        self.assertTrue(all(type(value) is int and value >= 0 for value in caught.exception.usage.values()))
        return caught.exception

    def test_disabled_by_default_and_missing_injection_make_no_calls(self):
        options = dict(provider="fake", provider_version="v1", normalizer_version="n1",
                       cache_namespace="dataset", cache=self.cache, normalize=lambda raw: raw,
                       transport=self.transport, budget=CallBudget(1))
        self.error(ProviderBatchOrchestrator(**options), "NOT_ENABLED")
        self.error(self.make(transport=None), "TRANSPORT_NOT_CONFIGURED")
        self.error(self.make(budget=None), "BUDGET_NOT_CONFIGURED")
        error = self.error(self.make(budget=CallBudget(0)), "BUDGET_EXHAUSTED")
        self.assertEqual(error.usage["actual_calls"], 0)
        self.assertEqual(self.transport.calls, [])

    def test_configuration_is_strict(self):
        for value in (None, True, -1, 1.0, "1"):
            with self.subTest(budget=value), self.assertRaises(ValueError):
                CallBudget(value)
        for options in ({"enabled": "true"}, {"max_requests": True}, {"max_requests": 0},
                        {"provider_version": ""}, {"normalizer_version": " "},
                        {"transport": object()}, {"budget": 1}, {"normalize": None}, {"retry_policy": {}}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                self.make(**options)

    def test_complete_canonical_keys_are_versioned_and_do_not_guess_semantics(self):
        orchestrator = self.make()
        original = ProviderRequest("fake.tool", {"nested": {"b": 2, "a": 1}, "items": ["x", "y"]})
        reordered = ProviderRequest("fake.tool", {"items": ["x", "y"], "nested": {"a": 1, "b": 2}})
        key = orchestrator.cache_key(original)
        self.assertEqual(key, orchestrator.cache_key(reordered))
        for request in (ProviderRequest("another.tool", original.arguments),
                        ProviderRequest("fake.tool", {**original.arguments, "page": 2}),
                        ProviderRequest("fake.tool", {**original.arguments, "items": ["y", "x"]})):
            self.assertNotEqual(key, orchestrator.cache_key(request))
        for identity in ({"provider": "other"}, {"provider_version": "v2"},
                         {"normalizer_version": "n2"}, {"cache_namespace": "another-account"}):
            self.assertNotEqual(key, self.make(**identity).cache_key(original))
        self.assertNotEqual(orchestrator.cache_key(ProviderRequest("fake.tool", {"q": "A "})),
                            orchestrator.cache_key(ProviderRequest("fake.tool", {"q": "a"})))

    def test_invalid_requests_preflight_entire_batch_without_calls(self):
        for invalid in (ProviderRequest("", {}), ProviderRequest("fake.tool", {1: "bad"}),
                        ProviderRequest("fake.tool", {"q": float("nan")}),
                        ProviderRequest("fake.tool", {"q": (1, 2)}),
                        ProviderRequest("fake.tool", {"q": object()}), {"tool_name": "fake.tool"}):
            self.error(self.make(), "INVALID_BATCH_OR_PROVIDER_DATA", [self.request, invalid])
        self.error(self.make(), "INVALID_BATCH", refresh="true")
        self.error(self.make(max_requests=1), "SAMPLE_LIMIT_EXCEEDED", [self.request, self.request])
        self.assertEqual(self.transport.calls, [])

    def test_same_batch_duplicates_and_cache_reuse_preserve_snapshot(self):
        orchestrator = self.make(budget=CallBudget(1))
        first = orchestrator.run([self.request, self.request])
        second = orchestrator.run([self.request])
        self.assertEqual(first["market_rows"], [{"keyword": "demo", "organic_rank": None}])
        self.assertEqual(first["usage"]["duplicates_suppressed"], 1)
        self.assertEqual(first["usage"]["actual_calls"], 1)
        self.assertEqual(second["usage"]["cache_hits"], 1)
        self.assertEqual(second["usage"]["actual_calls"], 0)
        self.assertEqual(first["provider_snapshot_version"], second["provider_snapshot_version"])
        self.assertEqual(len(self.transport.calls), 1)
        first["market_rows"][0]["keyword"] = "caller mutation"
        self.assertEqual(orchestrator.run([self.request])["market_rows"][0]["keyword"], "demo")

    def test_cache_can_be_reused_by_new_cache_only_instance(self):
        first = self.make().run([self.request])
        second = self.make(transport=None, budget=None).run([self.request])
        self.assertEqual(first["market_rows"], second["market_rows"])
        self.assertEqual(second["usage"]["cache_hits"], 1)
        self.assertEqual(second["usage"]["actual_calls"], 0)

    def test_refresh_deduplicates_and_overwrites_success(self):
        self.transport.responses = [{"keyword": "old"}, {"keyword": "new"}]
        orchestrator = self.make()
        first = orchestrator.run([self.request])
        fresh = orchestrator.run([self.request, self.request], refresh=True)
        self.assertNotEqual(first["provider_snapshot_version"], fresh["provider_snapshot_version"])
        self.assertEqual(fresh["market_rows"], [{"keyword": "new"}])
        self.assertEqual(fresh["usage"]["actual_calls"], 1)
        self.assertEqual(orchestrator.run([self.request])["market_rows"], fresh["market_rows"])
        self.assertEqual(len(self.transport.calls), 2)

    def test_failed_refresh_does_not_cache_failure_or_delete_previous_good_entry(self):
        orchestrator = self.make()
        first = orchestrator.run([self.request])
        self.transport.responses = [ValueError("fake-sensitive-detail")]
        error = self.error(orchestrator, "TRANSPORT_FAILED", refresh=True)
        self.assertNotIn("fake-sensitive-detail", str(error))
        self.assertEqual(orchestrator.run([self.request])["market_rows"], first["market_rows"])

    def test_expired_cache_and_changed_version_trigger_new_calls(self):
        orchestrator = self.make()
        with patch("worker.providers.cache.time.time", return_value=100):
            orchestrator.run([self.request])
        with patch("worker.providers.cache.time.time", return_value=111):
            result = orchestrator.run([self.request])
            self.assertEqual(result["usage"]["actual_calls"], 1)
            result = self.make(normalizer_version="v2").run([self.request])
            self.assertEqual(result["usage"]["actual_calls"], 1)
        self.assertEqual(len(self.transport.calls), 3)

    def test_response_and_exception_429_never_exceed_budget(self):
        class RateLimitError(RuntimeError):
            status_code = 429

        for response in ({"status": 429}, RateLimitError("fake-sensitive-detail")):
            with self.subTest(response=type(response)):
                transport = FakeTransport([response] * 5)
                budget = CallBudget(2)
                sleeps = []
                orchestrator = self.make(transport=transport, budget=budget,
                                         retry_policy=RetryPolicy(max_retries=10), sleep_fn=sleeps.append)
                error = self.error(orchestrator, "BUDGET_EXHAUSTED")
                self.assertEqual((len(transport.calls), budget.used), (2, 2))
                self.assertEqual(error.usage["actual_calls"], 2)
                self.assertEqual(error.usage["retries"], 1)
                self.assertEqual(error.usage["rate_limited"], 2)
                self.assertEqual(sleeps, [1])
                self.assertEqual(list(Path(self.directory.name).glob("*.json")), [])

    def test_retry_limit_and_success_usage(self):
        self.transport.responses = [{"status": 503}] * 3
        orchestrator = self.make(retry_policy=RetryPolicy(max_retries=1))
        error = self.error(orchestrator, "RETRIES_EXHAUSTED")
        self.assertEqual(error.usage["actual_calls"], 2)
        self.assertEqual(error.usage["failures"], 1)
        self.transport.responses = [{"status": 429}, {"keyword": "demo"}]
        result = orchestrator.run([self.request])
        self.assertEqual(result["usage"]["actual_calls"], 2)
        self.assertEqual(result["usage"]["retries"], 1)
        self.assertEqual(result["usage"]["rate_limited"], 1)
        self.assertEqual(result["usage"]["failures"], 0)

    def test_retry_after_metadata_overrides_static_backoff(self):
        class RetryAfterTransport(FakeTransport):
            def __init__(self):
                super().__init__([{"status": 429}, {"keyword": "demo"}])
                self.last_response_metadata = {}

            def call(self, tool_name, arguments):
                response = super().call(tool_name, arguments)
                self.last_response_metadata = {"retry-after": "7"} if response.get("status") == 429 else {}
                return response

        transport = RetryAfterTransport()
        sleeps = []
        result = self.make(transport=transport, sleep_fn=sleeps.append).run([self.request])
        self.assertEqual(result["usage"]["actual_calls"], 2)
        self.assertEqual(sleeps, [7.0])

    def test_failures_and_invalid_normalization_are_never_cached(self):
        for response in ({"status": 400}, {"status": 401}, {"status": 302}, {"error": {"message": "fake"}},
                         {"isError": True}, {"status": "200"}, ValueError("fake-sensitive-detail")):
            transport = FakeTransport([response])
            with self.assertRaises(ProviderBatchError) as caught:
                self.make(transport=transport).run([self.request])
            self.assertNotIn("fake-sensitive-detail", str(caught.exception))
            self.assertEqual(len(transport.calls), 1)
            self.assertEqual(list(Path(self.directory.name).glob("*.json")), [])
        for row in ([], None, {"rank": float("inf")}):
            with self.assertRaises(ProviderBatchError):
                self.make(normalize=lambda raw: row).run([self.request])
            self.assertEqual(list(Path(self.directory.name).glob("*.json")), [])

    def test_normalizer_and_sleep_exceptions_consume_attempts_without_leaking_details(self):
        def broken(_):
            raise ValueError("fake-sensitive-detail")

        budget = CallBudget(3)
        error = self.error(self.make(budget=budget, normalize=broken), "INVALID_BATCH_OR_PROVIDER_DATA")
        self.assertNotIn("fake-sensitive-detail", str(error))
        self.transport.responses = [{"status": 429}]
        error = self.error(self.make(budget=budget, sleep_fn=broken), "INVALID_BATCH_OR_PROVIDER_DATA")
        self.assertEqual(budget.used, 2)
        self.assertEqual(error.usage["actual_calls"], 1)
        self.assertEqual(list(Path(self.directory.name).glob("*.json")), [])

    def test_shared_budget_is_not_reset_between_runs_or_after_exceptions(self):
        budget = CallBudget(1)
        self.transport.responses = [RuntimeError("uncertain remote outcome")]
        orchestrator = self.make(budget=budget)
        self.error(orchestrator, "TRANSPORT_FAILED")
        error = self.error(orchestrator, "BUDGET_EXHAUSTED")
        self.assertEqual(error.usage["actual_calls"], 0)
        self.assertEqual(len(self.transport.calls), 1)

    def test_transports_cannot_mutate_the_next_retry_arguments(self):
        received = []

        class MutatingFake:
            def call(self, tool_name, arguments):
                received.append(json.loads(json.dumps(arguments)))
                arguments["nested"]["value"] = "mutated"
                return {"status": 429} if len(received) == 1 else {"keyword": "demo"}

        request = ProviderRequest("fake.tool", {"nested": {"value": "original"}})
        self.make(transport=MutatingFake()).run([request])
        self.assertEqual(received, [request.arguments, request.arguments])
        self.assertEqual(request.arguments["nested"]["value"], "original")

    def test_concurrent_runs_same_instance_reuse_cache(self):
        orchestrator = self.make(budget=CallBudget(1))
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(lambda _: orchestrator.run([self.request]), range(16)))
        self.assertEqual(len(self.transport.calls), 1)
        self.assertEqual(sum(result["usage"]["cache_hits"] for result in results), 15)

    def test_many_instances_share_atomic_budget_even_with_transport_exceptions(self):
        budget = CallBudget(7)
        transport = FakeTransport([RuntimeError("uncertain")] * 40)

        def run(index):
            orchestrator = self.make(transport=transport, budget=budget)
            try:
                return orchestrator.run([ProviderRequest("fake.tool", {"id": index})])
            except ProviderBatchError as exc:
                return exc

        with ThreadPoolExecutor(max_workers=12) as pool:
            results = list(pool.map(run, range(40)))
        self.assertEqual(budget.used, 7)
        self.assertEqual(len(transport.calls), 7)
        self.assertEqual(sum(result.usage["actual_calls"] for result in results), 7)

    def test_concurrent_429_retries_share_hard_budget(self):
        barrier = threading.Barrier(2)
        budget = CallBudget(3)
        calls = []
        lock = threading.Lock()

        class LimitedFake:
            def call(self, tool, arguments):
                with lock:
                    calls.append(arguments["id"])
                    first = calls.count(arguments["id"]) == 1
                if first:
                    barrier.wait(timeout=5)
                return {"status": 429}

        def run(index):
            orchestrator = self.make(transport=LimitedFake(), budget=budget)
            return self.error(orchestrator, "BUDGET_EXHAUSTED", [ProviderRequest("fake.tool", {"id": index})])

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(run, range(2)))
        self.assertEqual(len(calls), 3)
        self.assertEqual(budget.used, 3)
        self.assertEqual(sum(result.usage["actual_calls"] for result in results), 3)
        self.assertEqual(sum(result.usage["rate_limited"] for result in results), 3)

    def test_hook_fake_example_returns_exact_production_contract(self):
        # Fake schema deliberately belongs to this test, not a real provider.
        orchestrator = self.make(budget=CallBudget(1))

        def builder(parsed, effective_config):
            return [ProviderRequest("fake.tool", {"keyword": row["keyword"],
                                                   "marketplace": effective_config["marketplace"]})
                    for row in parsed["rows"]]

        provider_enricher = orchestrator.as_enricher(builder)
        result = provider_enricher({"rows": [{"keyword": "demo"}]}, {"marketplace": "US"})
        self.assertEqual(set(result), {"market_rows", "provider_snapshot_version", "usage"})
        self.assertIsInstance(result["provider_snapshot_version"], str)
        self.assertTrue(all(type(row) is dict for row in result["market_rows"]))
        self.assertTrue(all(type(value) is int and value >= 0 for value in result["usage"].values()))
        self.assertEqual(self.transport.calls, [("fake.tool", self.request.arguments)])

    def test_partial_batch_failure_preserves_only_successful_cache_and_no_success_result(self):
        orchestrator = self.make(budget=CallBudget(1))
        another = ProviderRequest("fake.tool", {"keyword": "another"})
        error = self.error(orchestrator, "BUDGET_EXHAUSTED", [self.request, another])
        self.assertEqual(error.usage["actual_calls"], 1)
        self.assertEqual(len(list(Path(self.directory.name).glob("*.json"))), 1)
        self.assertEqual(orchestrator.run([self.request])["usage"]["cache_hits"], 1)

    def test_hook_request_builder_errors_are_safe_and_make_no_calls(self):
        def broken_builder(parsed, effective_config):
            raise ValueError("fake-sensitive-detail")

        hook = self.make().as_enricher(broken_builder)
        with self.assertRaises(ProviderBatchError) as caught:
            hook({}, {})
        self.assertEqual(caught.exception.code, "REQUEST_BUILD_FAILED")
        self.assertNotIn("fake-sensitive-detail", str(caught.exception))
        self.assertEqual(caught.exception.usage["actual_calls"], 0)
        self.assertEqual(caught.exception.usage["failures"], 1)
        self.assertEqual(self.transport.calls, [])

    def test_corrupt_or_mismatched_cache_fails_closed_without_new_call(self):
        orchestrator = self.make()
        key = orchestrator.cache_key(self.request)
        self.cache.set(key, provider="fake", snapshot_version="wrong-version", data={"keyword": "wrong"})
        self.error(orchestrator, "INVALID_CACHE_ENTRY")
        self.assertEqual(self.transport.calls, [])
        result = orchestrator.run([self.request], refresh=True)
        self.assertEqual(result["usage"]["actual_calls"], 1)

    def test_empty_sample_makes_no_calls(self):
        result = self.make(transport=None, budget=None).run([])
        self.assertEqual(result["market_rows"], [])
        self.assertTrue(all(value == 0 for value in result["usage"].values()))


if __name__ == "__main__":
    unittest.main()
