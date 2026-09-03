import unittest

from worker.adapters.private_report_gateway import PrivateReportGatewayTransport
from worker.adapters.supabase_gateway import GatewayNotConfigured, SupabaseGateway
from worker.adapters.supabase_http import HttpResponse, PrivateReportError, SupabaseHttpTransport


class PrivateReportGatewayIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.calls = []
        def request(method, url, headers, payload):
            self.calls.append(headers["Authorization"])
            if "/auth/" in url:
                return HttpResponse(200, {"id": "user", "role": "authenticated"})
            if "/rest/" in url:
                return HttpResponse(200, [{"task_id": "task", "run_id": "run", "report_path": "task/run/master-table.json"}])
            return HttpResponse(200, {"schema_version": "report-0.2", "rows": []})
        client = SupabaseHttpTransport("https://example.invalid", "fake-public", "old-user", request, request)
        self.adapter = PrivateReportGatewayTransport(client)
        self.gateway = SupabaseGateway("https://example.invalid", self.adapter)

    def test_gateway_returns_content_with_only_current_callers_token(self):
        result = self.gateway.read_report("task", "run", "new-user")
        self.assertEqual([], result["content"]["rows"])
        self.assertEqual(["Bearer new-user"] * 3, self.calls)

    def test_unsupported_operations_do_not_make_network_calls(self):
        for operation in ("tasks.claim_pending", "configs.save", "tasks.create"):
            with self.assertRaises(GatewayNotConfigured):
                self.adapter.request(operation, {})
        self.assertEqual([], self.calls)

    def test_missing_or_elevated_session_never_reuses_template_token(self):
        with self.assertRaises(ValueError):
            self.adapter.request("reports.read_private", {"task_id": "task", "run_id": "run"})
        with self.assertRaises(ValueError):
            self.adapter.request("reports.read_private", {"task_id": "task", "run_id": "run", "access_token": None})
        with self.assertRaises(PrivateReportError):
            self.gateway.read_report("task", "run", "sb_secret_synthetic")
        self.assertEqual([], self.calls)
