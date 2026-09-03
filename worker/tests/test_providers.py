import unittest
import math

from worker.providers.base import ProviderContract, RetryPolicy
from worker.providers.config_validation import validate_config
from worker.rule_engine.engine import load_default_config


class ProviderTests(unittest.TestCase):
    def test_estimate_cache_and_snapshot_are_deterministic(self):
        provider = ProviderContract()
        self.assertEqual(provider.estimate(["a", "b"]), 2)
        self.assertEqual(provider.cache_key("a", "B0A", "US"), provider.cache_key("a", "B0A", "US"))
        first = provider.snapshot([{"keyword": "a", "organic_rank": None}])
        second = provider.snapshot([{"keyword": "a", "organic_rank": None}])
        self.assertEqual(first.snapshot_version, second.snapshot_version)
        with self.assertRaisesRegex(RuntimeError, "no paid call"):
            provider.fetch("tools/list", {})

    def test_429_is_retried_with_bounded_backoff_and_usage_counts(self):
        class Transport:
            def __init__(self):
                self.calls = 0

            def call(self, *_):
                self.calls += 1
                return {"status": 429} if self.calls == 1 else {"ok": True}

        transport = Transport()
        sleeps = []
        provider = ProviderContract(transport, RetryPolicy(max_retries=2, backoff_seconds=(2, 4)), sleeps.append)
        self.assertEqual(provider.fetch("estimate", {}), {"ok": True})
        self.assertEqual(transport.calls, 2)
        self.assertEqual(sleeps, [2])
        self.assertEqual(provider.usage.rate_limited, 1)
        self.assertEqual(provider.usage.actual_calls, 2)

    def test_retry_after_metadata_overrides_static_backoff(self):
        class Transport:
            last_response_metadata = {"Retry-After": "7", "x-cost-credits": "1"}

            def __init__(self):
                self.calls = 0

            def call(self, *_):
                self.calls += 1
                return {"status": 429} if self.calls == 1 else {"ok": True}

        sleeps = []
        provider = ProviderContract(Transport(), RetryPolicy(max_retries=1, backoff_seconds=(1,)), sleeps.append)
        self.assertEqual(provider.fetch("estimate", {}), {"ok": True})
        self.assertEqual(sleeps, [7.0])

    def test_final_429_is_counted_as_rate_limited(self):
        class Transport:
            def call(self, *_):
                return {"status": 429}

        sleeps = []
        provider = ProviderContract(Transport(), RetryPolicy(max_retries=1, backoff_seconds=(1,)), sleeps.append)
        with self.assertRaisesRegex(RuntimeError, "status=429"):
            provider.fetch("estimate", {})
        self.assertEqual(provider.usage.actual_calls, 2)
        self.assertEqual(provider.usage.rate_limited, 2)
        self.assertEqual(provider.usage.failures, 1)
        self.assertEqual(sleeps, [1])

    def test_exception_429_is_counted_without_external_retry_on_final_attempt(self):
        class RateLimitError(RuntimeError):
            status_code = 429

        class Transport:
            def call(self, *_):
                raise RateLimitError("limited")

        provider = ProviderContract(Transport(), RetryPolicy(max_retries=0), lambda _delay: None)
        with self.assertRaises(RateLimitError):
            provider.fetch("estimate", {})
        self.assertEqual(provider.usage.actual_calls, 1)
        self.assertEqual(provider.usage.rate_limited, 1)
        self.assertEqual(provider.usage.failures, 1)

    def test_5xx_is_retried_and_final_failure_is_bounded(self):
        class Transport:
            def call(self, *_):
                return {"status": 503}

        sleeps = []
        provider = ProviderContract(Transport(), RetryPolicy(max_retries=2, backoff_seconds=(1, 2)), sleeps.append)
        with self.assertRaisesRegex(RuntimeError, "status=503"):
            provider.fetch("estimate", {})
        self.assertEqual(provider.usage.actual_calls, 3)
        self.assertEqual(provider.usage.rate_limited, 0)
        self.assertEqual(provider.usage.failures, 1)
        self.assertEqual(sleeps, [1, 2])

    def test_default_config_passes_validation(self):
        self.assertEqual(validate_config(load_default_config()), [])

    def test_missing_or_malformed_config_returns_validation_errors(self):
        self.assertIn("config must be an object", validate_config(None))
        config = load_default_config()
        config["market"]["high_opportunity_min"] = 2
        config["evidence"]["preliminary_clicks_min"] = 30
        errors = validate_config(config)
        self.assertTrue(any("market.high_opportunity_min" in error for error in errors))
        self.assertTrue(any("click boundaries" in error for error in errors))

    def test_retry_policy_rejects_unsafe_values(self):
        with self.assertRaises(ValueError):
            RetryPolicy(max_retries=-1)
        with self.assertRaises(ValueError):
            RetryPolicy(backoff_seconds=(float("nan"),))

    def test_missing_transport_is_recorded_without_a_paid_call(self):
        provider = ProviderContract()
        with self.assertRaisesRegex(RuntimeError, "no paid call"):
            provider.fetch("tools/list", {})
        self.assertEqual(provider.usage.actual_calls, 0)
        self.assertEqual(provider.usage.failures, 1)

    def test_invalid_acos_boundaries_fail(self):
        config = load_default_config()
        config["acos"]["target"] = 0.4
        self.assertTrue(any("boundaries" in error for error in validate_config(config)))

    def test_non_finite_and_boolean_thresholds_fail(self):
        config = load_default_config()
        config["acos"]["target"] = math.nan
        config["stop_loss"]["zero_order_clicks"] = True
        errors = validate_config(config)
        self.assertTrue(any("acos.target" in error for error in errors))
        self.assertTrue(any("stop_loss.zero_order_clicks" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
