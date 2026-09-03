import unittest

from worker.providers.mcp_protocol import find_tool, parse_tools_list, tools_list_request


class McpProtocolTests(unittest.TestCase):
    def test_request_and_schema_extraction(self):
        self.assertEqual(tools_list_request()["method"], "tools/list")
        tools = parse_tools_list({"jsonrpc": "2.0", "id": 1, "result": {"tools": [{"name": "keyword_info", "inputSchema": {"type": "object"}}]}})
        self.assertEqual(find_tool(tools, "keyword_info")["inputSchema"]["type"], "object")

    def test_error_response_is_not_silently_accepted(self):
        with self.assertRaises(RuntimeError):
            parse_tools_list({"jsonrpc": "2.0", "id": 1, "error": {"code": -1, "message": "bad"}})


if __name__ == "__main__":
    unittest.main()

