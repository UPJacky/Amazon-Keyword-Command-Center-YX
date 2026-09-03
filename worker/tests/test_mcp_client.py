import tempfile
import unittest
from pathlib import Path

from worker.providers.base import RetryPolicy
from worker.providers.mcp_client import McpProvider


class FakeTransport:
    def __init__(self):
        self.calls = []

    def call(self, operation, payload):
        self.calls.append((operation, payload))
        return {"jsonrpc": "2.0", "id": payload["id"], "result": {"tools": [{"name": "keyword_info", "inputSchema": {"type": "object"}}]}}


class McpClientTests(unittest.TestCase):
    def test_discovery_uses_tools_list_and_can_save_snapshot(self):
        transport = FakeTransport()
        provider = McpProvider(transport)
        tools = provider.discover_tools()
        self.assertEqual(tools[0]["name"], "keyword_info")
        self.assertEqual(transport.calls[0][1]["method"], "tools/list")
        with tempfile.TemporaryDirectory() as directory:
            path = provider.write_tools_snapshot(tools, Path(directory) / "tools.json")
            self.assertTrue(path.is_file())

    def test_tools_list_uses_bounded_retry_and_usage(self):
        class RetryTransport:
            def __init__(self):
                self.calls = 0

            def call(self, operation, payload):
                self.calls += 1
                if self.calls == 1:
                    return {"status": 429}
                return {"jsonrpc": "2.0", "id": payload["id"], "result": {"tools": []}}

        sleeps = []
        transport = RetryTransport()
        provider = McpProvider(transport, RetryPolicy(max_retries=1, backoff_seconds=(3,)), sleeps.append)
        self.assertEqual(provider.discover_tools(), [])
        self.assertEqual(transport.calls, 2)
        self.assertEqual(provider.usage.actual_calls, 2)
        self.assertEqual(provider.usage.rate_limited, 1)
        self.assertEqual(sleeps, [3])

    def test_tools_list_final_429_preserves_limit_usage_and_failure(self):
        class RetryTransport:
            def call(self, *_):
                return {"status": 429}

        sleeps = []
        provider = McpProvider(RetryTransport(), RetryPolicy(max_retries=1, backoff_seconds=(2,)), sleeps.append)
        with self.assertRaisesRegex(RuntimeError, "status=429"):
            provider.discover_tools()
        self.assertEqual(provider.usage.actual_calls, 2)
        self.assertEqual(provider.usage.rate_limited, 2)
        self.assertEqual(provider.usage.failures, 1)
        self.assertEqual(sleeps, [2])


if __name__ == "__main__":
    unittest.main()
