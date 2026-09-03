import tempfile
import unittest
import os
from pathlib import Path
from unittest.mock import patch

from worker.providers.cache import ProviderCache


class ProviderCacheTests(unittest.TestCase):
    def test_hit_and_expiry_are_explicit(self):
        with tempfile.TemporaryDirectory() as directory:
            cache = ProviderCache(directory, ttl_seconds=10)
            cache.set("key1", provider="mcp", snapshot_version="s1", data={"x": 1}, now=100)
            self.assertEqual(cache.get("key1", now=109)["data"], {"x": 1})
            self.assertIsNone(cache.get("key1", now=111))

    def test_invalid_key_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            cache = ProviderCache(directory, ttl_seconds=10)
            for key in ("../escape", "file:stream", "C:drive", "x%2fother", "key\n", None):
                with self.subTest(key=key), self.assertRaises(ValueError):
                    cache.get(key)

    def test_invalid_ttl_and_timestamps_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            for ttl in (True, float("nan"), float("inf"), -1, "10"):
                with self.assertRaises(ValueError):
                    ProviderCache(directory, ttl)
            cache = ProviderCache(directory, 10)
            for timestamp in (True, float("nan"), float("inf"), -1):
                with self.assertRaises(ValueError):
                    cache.set("key", provider="fake", snapshot_version="v1", data={}, now=timestamp)

    def test_cache_rechecks_link_boundary_after_initialization(self):
        with tempfile.TemporaryDirectory() as directory:
            cache = ProviderCache(directory, 10)
            with patch("worker.providers.cache.contains_link_or_reparse", return_value=True):
                with self.assertRaises(ValueError):
                    cache.get("key")
                with self.assertRaises(ValueError):
                    cache.set("key", provider="fake", snapshot_version="v1", data={})

    def test_future_entry_is_not_treated_as_fresh_forever(self):
        with tempfile.TemporaryDirectory() as directory:
            cache = ProviderCache(directory, 10)
            cache.set("key", provider="fake", snapshot_version="v1", data={}, now=200)
            self.assertIsNone(cache.get("key", now=100))

    def test_refresh_publishes_complete_entry_atomically(self):
        with tempfile.TemporaryDirectory() as directory:
            cache = ProviderCache(directory, ttl_seconds=10)
            cache.set("key1", provider="fake", snapshot_version="old", data={"x": 1}, now=100)
            replace = os.replace

            def inspect_before_publish(source, destination):
                self.assertEqual(cache.get("key1", now=101)["data"], {"x": 1})
                self.assertTrue(Path(source).is_file())
                replace(source, destination)

            with patch("worker.providers.cache.os.replace", side_effect=inspect_before_publish):
                cache.set("key1", provider="fake", snapshot_version="new", data={"x": 2}, now=101)
            self.assertEqual(cache.get("key1", now=101)["data"], {"x": 2})
            self.assertEqual(len(list(Path(directory).iterdir())), 1)

    def test_failed_publish_preserves_previous_entry_and_cleans_temporary_file(self):
        with tempfile.TemporaryDirectory() as directory:
            cache = ProviderCache(directory, ttl_seconds=10)
            cache.set("key1", provider="fake", snapshot_version="old", data={"x": 1}, now=100)
            with patch("worker.providers.cache.os.replace", side_effect=OSError("fake failure")):
                with self.assertRaises(OSError):
                    cache.set("key1", provider="fake", snapshot_version="new", data={"x": 2}, now=100)
            self.assertEqual(cache.get("key1", now=100)["data"], {"x": 1})
            self.assertEqual(len(list(Path(directory).iterdir())), 1)


if __name__ == "__main__":
    unittest.main()
