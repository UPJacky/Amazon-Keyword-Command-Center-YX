import io
import unittest
from urllib.error import URLError

from worker.providers.sorftime_transport import SorftimeTransport


class Response(io.BytesIO):
    headers = {"Content-Type": "text/event-stream"}


class SorftimeTransportTests(unittest.TestCase):
    def test_sse_notification_then_matching_response(self):
        def open_request(request, timeout):
            self.assertIsNone(request.get_header("Authorization"))
            return Response(b'event: message\ndata: {"jsonrpc":"2.0","method":"notifications/progress"}\n\nevent: message\ndata: {"jsonrpc":"2.0","id":1,"result":{"tools":[]}}\n\n')
        transport = SorftimeTransport("https://mcp.sorftime.com?key=private", opener=open_request)
        self.assertEqual({"tools": []}, transport.call("tools/list", {}))
        self.assertNotIn("private", repr(transport))

    def test_errors_never_expose_endpoint(self):
        def fail(*args, **kwargs):
            raise URLError("https://mcp.sorftime.com?key=private")
        with self.assertRaisesRegex(RuntimeError, "^Sorftime request or response failed$"):
            SorftimeTransport("https://mcp.sorftime.com?key=private", opener=fail).call("tools/list", {})

    def test_wrong_rpc_id_is_rejected(self):
        transport = SorftimeTransport("https://mcp.sorftime.com?key=private", opener=lambda *a, **k: Response(b'data: {"jsonrpc":"2.0","id":2,"result":{}}\n\n'))
        with self.assertRaises(RuntimeError):
            transport.call("tools/list", {})

    def test_configuration_rejects_other_hosts_and_nonfinite_timeout(self):
        for endpoint in ("http://mcp.sorftime.com?key=x", "https://other.example?key=x", "https://mcp.sorftime.com?key="):
            with self.assertRaises(ValueError):
                SorftimeTransport(endpoint)
        with self.assertRaises(ValueError):
            SorftimeTransport("https://mcp.sorftime.com?key=x", timeout=float("nan"))
