"""Private report contract tests: synthetic identities, no network transport."""

import base64
from dataclasses import replace
import json
import traceback
import unittest
from unittest.mock import patch

from worker.adapters.supabase_http import (
    HttpResponse, HttpTransportNotConfigured, PrivateReportError, SupabaseHttpTransport,
)


class SupabasePrivateReportTests(unittest.TestCase):
    def setUp(self):
        # Any accidental automatic HTTP client fails the suite.
        guard = patch("socket.socket", side_effect=AssertionError("network prohibited"))
        guard.start()
        self.addCleanup(guard.stop)
        self.calls = []
        self.auth = HttpResponse(200, {"id": "user-a", "role": "authenticated"})
        self.row = {"task_id": "task-1", "run_id": "run-1", "report_path": "task-1/run-1/master-table.json"}
        self.metadata = HttpResponse(200, [self.row])
        self.object = HttpResponse(200, {"schema_version": "report-0.2", "rows": []})
        self.transport = SupabaseHttpTransport(
            "https://example.supabase.co", "fake-public-key", "fake-user-token",
            self.request, self.request_object,
        )

    def deliver(self, response):
        if isinstance(response, Exception):
            raise response
        return response

    def request(self, method, url, headers, payload):
        self.calls.append((method, url, headers, payload))
        return self.deliver(self.auth if "/auth/" in url else self.metadata)

    def request_object(self, method, url, headers, payload):
        self.calls.append((method, url, headers, payload))
        return self.deliver(self.object)

    def read(self):
        return self.transport.read_report_content("task-1", "run-1")

    def assert_denied(self, count):
        with self.assertRaises(PrivateReportError) as caught:
            self.read()
        self.assertEqual(len(self.calls), count)
        rendered = "".join(traceback.format_exception(caught.exception))
        self.assertNotIn("fake-user-token", rendered)
        self.assertNotIn("fake-public-key", rendered)

    def test_authorizes_before_private_object_read_with_same_user_token(self):
        result = self.read()
        self.assertEqual(result, {**self.row, "content": self.object.body})
        self.assertEqual(len(self.calls), 3)
        self.assertEqual(self.calls[0][1], "https://example.supabase.co/auth/v1/user")
        self.assertEqual(self.calls[1][1], "https://example.supabase.co/rest/v1/task_runs?task_id=eq.task-1&run_id=eq.run-1&select=task_id,run_id,report_path&limit=2")
        self.assertEqual(self.calls[2][1], "https://example.supabase.co/storage/v1/object/authenticated/reports/task-1/run-1/master-table.json")
        for index, (method, url, headers, payload) in enumerate(self.calls):
            self.assertEqual(method, "GET")
            self.assertIsNone(payload)
            self.assertEqual(headers["Authorization"], "Bearer fake-user-token")
            self.assertEqual(headers["apikey"], "fake-public-key")
            self.assertNotIn("/sign/", url)
            self.assertNotIn("/public/", url)
            if index == 1:
                self.assertEqual(headers["Accept-Profile"], "public")
                self.assertEqual(headers["Content-Profile"], "public")
            else:
                self.assertNotIn("Accept-Profile", headers)
                self.assertNotIn("Content-Profile", headers)

    def test_json_bytes_object_response(self):
        self.object = HttpResponse(200, b'{"rows": [], "schema_version": "report-0.2"}')
        self.assertEqual(self.read()["content"]["rows"], [])

    def test_second_authenticated_user_cannot_reuse_first_users_report_authorization(self):
        self.read()
        self.calls.clear()
        self.transport = replace(self.transport, access_token="fake-second-user")
        self.auth = HttpResponse(200, {"id": "user-b", "role": "authenticated"})
        self.metadata = HttpResponse(200, [])  # RLS hides user A's run from B.
        self.assert_denied(2)
        for _, _, headers, _ in self.calls:
            self.assertEqual(headers["Authorization"], "Bearer fake-second-user")

    def test_configured_private_bucket_is_used_without_taking_bucket_from_metadata(self):
        self.transport = replace(self.transport, report_bucket="private-reports")
        self.row["report_bucket"] = "attacker-bucket"
        self.read()
        self.assertIn("/authenticated/private-reports/", self.calls[-1][1])

    def test_missing_either_transport_sends_nothing_including_auth(self):
        for changes in ({"object_request_fn": None}, {"request_fn": None}, {"object_request_fn": False}):
            with self.subTest(changes=changes):
                with self.assertRaises(HttpTransportNotConfigured):
                    replace(self.transport, **changes).read_report_content("task-1", "run-1")
                self.assertEqual(self.calls, [])

    def test_invalid_local_inputs_send_nothing(self):
        for token in (None, "", "  ", "fake-user-token\r\n", 123):
            with self.subTest(token=token), self.assertRaises(ValueError):
                replace(self.transport, access_token=token).read_report_content("task-1", "run-1")
        for task, run in (("../task", "run-1"), ("task-1", "run&x=1"), (None, "run-1")):
            with self.assertRaises(ValueError):
                self.transport.read_report_content(task, run)
        for bucket in ("../reports", "https://evil.invalid", "reports/public", "reports%2fpublic"):
            with self.assertRaises(ValueError):
                replace(self.transport, report_bucket=bucket).read_report_content("task-1", "run-1")
        self.assertEqual(self.calls, [])

    def test_elevated_credentials_rejected_without_network(self):
        claims = base64.urlsafe_b64encode(json.dumps({"role": "service_role"}).encode()).decode().rstrip("=")
        for credential in ("sb_secret_synthetic", f"header.{claims}.signature"):
            for field in ("access_token", "public_key"):
                with self.subTest(field=field), self.assertRaises(PrivateReportError):
                    replace(self.transport, **{field: credential}).read_report_content("task-1", "run-1")
        self.assertEqual(self.calls, [])

    def test_private_report_rejects_plaintext_origin_before_auth(self):
        with self.assertRaises(PrivateReportError):
            replace(self.transport, base_url="http://example.invalid").read_report_content("task-1", "run-1")
        self.assertEqual([], self.calls)

    def test_auth_expiry_denial_error_bodies_and_malformed_success_stop_before_metadata(self):
        for response in (
            HttpResponse(401, {"message": "fake-user-token expired"}),
            HttpResponse(403, {}), HttpResponse(302, "redirect"),
            HttpResponse(200, {"error": "fake-user-token"}),
            HttpResponse(200, {"id": "user-a", "role": "service_role"}),
            HttpResponse(200, {"id": "user-a"}), HttpResponse(200, {"id": "", "role": "authenticated"}),
            HttpResponse(200, []), HttpResponse(200, None), {"id": "user-a"},
            RuntimeError("fake-user-token fake-public-key"),
        ):
            with self.subTest(response=response):
                self.calls.clear()
                self.auth = response
                self.assert_denied(1)

    def test_rls_denied_empty_or_ambiguous_metadata_stops_before_object(self):
        for response in (
            HttpResponse(200, []), HttpResponse(200, None), HttpResponse(200, [None]),
            HttpResponse(200, [self.row, self.row]), HttpResponse(200, self.row),
            HttpResponse(200, {"message": "fake-user-token"}),
            HttpResponse(401, {}), HttpResponse(403, {}), HttpResponse(500, "fake-user-token"),
            {"body": [self.row]}, HttpResponse(True, [self.row]), HttpResponse("200", [self.row]),
            RuntimeError("fake-user-token fake-public-key"),
        ):
            with self.subTest(response=response):
                self.calls.clear()
                self.metadata = response
                self.assert_denied(2)

    def test_returned_metadata_must_match_both_requested_identifiers(self):
        for row in ({**self.row, "task_id": "task-2"}, {**self.row, "run_id": "run-2"},
                    {**self.row, "error": "fake-user-token"},
                    {"report_path": self.row["report_path"]}, {}):
            with self.subTest(row=row):
                self.calls.clear()
                self.metadata = HttpResponse(200, [row])
                self.assert_denied(2)

    def test_bucket_relative_path_rejects_cross_run_traversal_and_encoding(self):
        for path in (
            None, "", 123, "https://evil.invalid/task-1/run-1/master-table.json",
            "//evil.invalid/x.json", "/task-1/run-1/master-table.json", "C:\\task-1\\run-1\\master-table.json",
            "reports/task-1/run-1/master-table.json", "task-2/run-1/master-table.json",
            "task-1/run-2/master-table.json", "task-1/run-10/master-table.json",
            "task-1/run-1/../run-2/master-table.json", "task-1/run-1/./master-table.json",
            "task-1/run-1/%2e%2e%2frun-2%2fmaster-table.json", "task-1/run-1/%252e%252e.json",
            "task-1/run-1/%6daster-table.json", "task-1/run-1/master-table.json?token=x",
            "task-1/run-1/master-table.json#x", "task-1/run-1/master-table.json\x00",
            "task-1/run-1/master-table.json\n", "task-1/run-1/master-table.json ",
            "task-1/run-1//master-table.json", "task-1/run-1/a\\b.json",
            "task-1/run-1/\uff0emaster-table.json", "task-1/run-1/master-table.html",
        ):
            with self.subTest(path=path):
                self.calls.clear()
                self.row["report_path"] = path
                self.assert_denied(2)

    def test_storage_expiry_not_found_errors_and_invalid_objects_fail_closed(self):
        for response in (
            HttpResponse(401, "fake-user-token"), HttpResponse(403, {}), HttpResponse(404, {}),
            HttpResponse(302, "https://evil.invalid"), HttpResponse(500, {"message": "fake-user-token"}),
            HttpResponse(200, {"error": "fake-user-token"}), HttpResponse(200, {"statusCode": "404"}),
            HttpResponse(200, {"task_id": "task-2", "rows": []}),
            HttpResponse(200, {"run_id": "run-2", "rows": []}),
            HttpResponse(200, b'{"message":"fake-user-token"}'), HttpResponse(200, b"not JSON"),
            HttpResponse(200, b"\xff"), HttpResponse(200, b"null"), HttpResponse(200, b"[]"),
            HttpResponse(200, None), HttpResponse(200, {}), HttpResponse(200, []),
            HttpResponse(200, "https://example.invalid/public/report.json"),
            {"rows": []}, RuntimeError("fake-user-token fake-public-key"),
        ):
            with self.subTest(response=response):
                self.calls.clear()
                self.object = response
                self.assert_denied(3)

    def test_transport_and_response_repr_do_not_expose_credentials_or_bodies(self):
        self.assertNotIn("fake-user-token", repr(self.transport))
        self.assertNotIn("fake-public-key", repr(self.transport))
        self.assertNotIn("fake-user-token", repr(HttpResponse(401, "fake-user-token")))


if __name__ == "__main__":
    unittest.main()
