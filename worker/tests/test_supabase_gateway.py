import unittest

from worker.adapters.supabase_gateway import GatewayNotConfigured, SupabaseGateway


class SupabaseGatewayTests(unittest.TestCase):
    def test_unconfigured_gateway_does_not_make_network_request(self):
        gateway = SupabaseGateway()
        with self.assertRaises(GatewayNotConfigured):
            gateway.create_task({"task_id": "t1"})

    def test_access_token_is_required(self):
        with self.assertRaises(ValueError):
            SupabaseGateway().get_current_user("")

    def test_private_report_identifiers_are_strictly_validated(self):
        with self.assertRaises(ValueError):
            SupabaseGateway().read_report("task&status=eq.failed", "run-1", "user-token")

    def test_private_report_requires_access_token(self):
        with self.assertRaises(ValueError):
            SupabaseGateway().read_report("task-1", "run-1", "")


if __name__ == "__main__":
    unittest.main()
