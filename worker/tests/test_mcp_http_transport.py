import json
import os
import tempfile
import unittest
from pathlib import Path
from urllib.error import HTTPError
from unittest.mock import patch

from worker.providers.mcp_http_transport import McpHttpTransport


class FakeResponse:
    def __init__(self, body, content_type="application/json", headers=None):
        self.body = body
        self.headers = {"Content-Type": content_type, **(headers or {})}

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, _limit):
        return self.body


class FakeOpener:
    def __init__(self, response):
        self.response = response
        self.request = None
        self.timeout = None

    def __call__(self, request, timeout):
        self.request = request
        self.timeout = timeout
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


class McpHttpTransportTests(unittest.TestCase):
    def test_sends_jsonrpc_with_auth_without_exposing_token_in_repr(self):
        opener = FakeOpener(FakeResponse(b'{"result":{"tools":[]}}', headers={"X-Cost-Credits": "1", "Authorization": "server-secret", "X-Unlisted": "do-not-copy"}))
        transport = McpHttpTransport("https://provider.example/mcp", "private-token", opener=opener)
        result = transport.call("jsonrpc", {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}})
        self.assertEqual(result["result"]["tools"], [])
        self.assertEqual(opener.request.full_url, "https://provider.example/mcp")
        self.assertEqual(opener.request.get_header("Authorization"), "Bearer private-token")
        self.assertNotIn("private-token", repr(transport))
        self.assertEqual(transport.last_response_metadata, {"content-type": "application/json", "x-cost-credits": "1"})
        self.assertEqual(json.loads(opener.request.data), {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}})

    def test_translates_http_status_without_reading_error_body(self):
        error = HTTPError("https://provider.example/mcp", 429, "rate limited", {"Retry-After": "7", "X-RateLimit-Remaining": "0", "Authorization": "server-secret"}, None)
        opener = FakeOpener(error)
        transport = McpHttpTransport("https://provider.example/mcp", "private-token", opener=opener)
        self.assertEqual(transport.call("jsonrpc", {}), {"status": 429})
        self.assertEqual(transport.last_response_metadata, {"retry-after": "7", "x-ratelimit-remaining": "0"})

    def test_omits_invalid_or_oversized_response_metadata(self):
        opener = FakeOpener(FakeResponse(b'{"result":{}}', headers={"Retry-After": "7\nleak", "X-Api-Version": "v2", "X-Cost-Credits": "x" * 257}))
        transport = McpHttpTransport("https://provider.example/mcp", "private-token", opener=opener)
        transport.call("jsonrpc", {})
        self.assertEqual(transport.last_response_metadata, {"content-type": "application/json", "x-api-version": "v2"})

    def test_supports_event_stream_data(self):
        opener = FakeOpener(FakeResponse(b"event: message\ndata: {\"result\":{\"tools\":[]}}\n\n", "text/event-stream"))
        transport = McpHttpTransport("https://provider.example/mcp", "private-token", opener=opener)
        self.assertEqual(transport.call("jsonrpc", {})["result"]["tools"], [])

    def test_rejects_unsafe_endpoint_and_token(self):
        with self.assertRaises(ValueError):
            McpHttpTransport("http://provider.example/mcp", "token")
        with self.assertRaises(ValueError):
            McpHttpTransport("https://provider.example/mcp?token=secret", "token")
        with self.assertRaises(ValueError):
            McpHttpTransport("https://provider.example/mcp", "token\nleak")

    def test_missing_config_probe_is_offline_safe(self):
        from scripts.probe_provider import main

        with patch.dict(os.environ, {"XYDC_MCP_URL": "", "XYDC_MCP_TOKEN": ""}):
            self.assertEqual(main(["--output", "unused-evidence.json"]), 2)

    def test_probe_persists_only_transport_response_metadata(self):
        from scripts import probe_provider

        class FakeProbeTransport:
            def __init__(self, *_args, **_kwargs):
                self.last_response_metadata = {}

            def call(self, tool_name, _arguments):
                if tool_name == "jsonrpc":
                    self.last_response_metadata = {"content-type": "application/json", "x-cost-credits": "1", "Authorization": "never-copy"}
                    return {"jsonrpc": "2.0", "id": 1, "result": {"tools": [{"name": "keyword_info", "inputSchema": {"type": "object"}}]}}
                self.last_response_metadata = {"content-type": "application/json", "retry-after": "7", "X-Unlisted": "never-copy"}
                return {"jsonrpc": "2.0", "result": {"content": []}}

        with tempfile.TemporaryDirectory() as directory, patch.object(probe_provider, "McpHttpTransport", FakeProbeTransport), patch.dict(os.environ, {"XYDC_MCP_URL": "https://provider.example/mcp", "XYDC_MCP_TOKEN": "private-token"}):
            output = Path(directory) / "evidence.json"
            self.assertEqual(probe_provider.main(["--output", str(output), "--tool", "keyword_info"]), 0)
            evidence = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(evidence["response_metadata_after_tools_list"], {"content-type": "application/json", "x-cost-credits": "1"})
        self.assertEqual(evidence["response_metadata_after_sample"], {"content-type": "application/json", "retry-after": "7"})
        self.assertNotIn("Authorization", json.dumps(evidence, ensure_ascii=False))
        self.assertNotIn("never-copy", json.dumps(evidence, ensure_ascii=False))


if __name__ == "__main__":
    unittest.main()
