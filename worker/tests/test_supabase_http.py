import unittest

from worker.adapters.supabase_http import HttpTransportNotConfigured, SupabaseHttpTransport


class SupabaseHttpTests(unittest.TestCase):
    def test_default_transport_does_not_send(self):
        with self.assertRaises(ValueError):
            SupabaseHttpTransport().auth_user()
        with self.assertRaises(HttpTransportNotConfigured):
            SupabaseHttpTransport(access_token="user-token").auth_user()

    def test_injected_request_receives_expected_auth_headers_and_path(self):
        calls = []

        def request(method, url, headers, payload):
            calls.append((method, url, headers, payload))
            return {"ok": True}

        transport = SupabaseHttpTransport("https://example.supabase.co", "public-key", "user-token", request)
        transport.insert_task({"task_id": "t1"})
        self.assertEqual(calls[0][0], "POST")
        self.assertEqual(calls[0][1], "https://example.supabase.co/rest/v1/tasks")
        self.assertEqual(calls[0][2]["Authorization"], "Bearer user-token")
        self.assertEqual(calls[0][2]["Accept-Profile"], "public")
        self.assertEqual(calls[0][2]["Content-Profile"], "public")
        self.assertEqual(calls[0][3], {"task_id": "t1"})

    def test_profiles_are_explicit_for_rest_only_and_metadata_is_compatible(self):
        calls = []
        metadata = [{"report_path": "task-1/run-1/master-table.json"}]

        def request(method, url, headers, payload):
            calls.append((url, headers))
            return metadata

        transport = SupabaseHttpTransport("https://example.supabase.co", "public-key", "user-token", request)
        transport.auth_user()
        transport.claim_tasks()
        self.assertIs(transport.read_report("task-1", "run-1"), metadata)
        self.assertTrue(calls[-1][0].endswith("&select=report_path"))
        self.assertNotIn("Accept-Profile", calls[0][1])
        self.assertNotIn("Content-Profile", calls[0][1])
        for _, headers in calls[1:]:
            self.assertEqual(headers["Accept-Profile"], "public")
            self.assertEqual(headers["Content-Profile"], "public")

    def test_report_query_rejects_injected_identifiers(self):
        transport = SupabaseHttpTransport("https://example.supabase.co", "public-key", request_fn=lambda *args: {})
        with self.assertRaises(ValueError):
            transport.read_report("task&status=eq.failed", "run-1")

    def test_base_url_must_be_absolute_http_url(self):
        transport = SupabaseHttpTransport("not-a-url", "public-key", request_fn=lambda *args: {})
        with self.assertRaises(ValueError):
            transport.auth_user()

    def test_base_url_rejects_credentials_and_query_components(self):
        for base_url in ("https://user:pass@example.supabase.co", "https://example.supabase.co/?token=secret", "https://example.supabase.co/base", "https://example.supabase.co\n.evil", "https://example.supabase.co\x85.evil", "https://[::1"):
            transport = SupabaseHttpTransport(base_url, "public-key", request_fn=lambda *args: {})
            with self.assertRaises(ValueError):
                transport.auth_user()

    def test_base_url_must_be_string_and_rejects_unicode_controls(self):
        for base_url in (123, "https://example.supabase.co\u0085"):
            transport = SupabaseHttpTransport(base_url, "public-key", request_fn=lambda *args: {})
            with self.assertRaises(ValueError):
                transport.auth_user()

    def test_header_values_reject_crlf(self):
        transport = SupabaseHttpTransport("https://example.supabase.co", "public\n-key", request_fn=lambda *args: {})
        with self.assertRaises(ValueError):
            transport.auth_user()

    def test_header_values_reject_other_http_controls(self):
        for value in ("public\x00-key", "public\x85-key"):
            transport = SupabaseHttpTransport("https://example.supabase.co", value, request_fn=lambda *args: {})
            with self.assertRaises(ValueError):
                transport.auth_user()

    def test_header_values_must_be_strings(self):
        transport = SupabaseHttpTransport("https://example.supabase.co", 123, request_fn=lambda *args: {})
        with self.assertRaises(ValueError):
            transport.auth_user()

    def test_private_operations_require_access_token(self):
        transport = SupabaseHttpTransport("https://example.supabase.co", "public-key", request_fn=lambda *args: {})
        with self.assertRaises(ValueError):
            transport.auth_user()
        with self.assertRaises(ValueError):
            transport.read_report("task-1", "run-1")


if __name__ == "__main__":
    unittest.main()
