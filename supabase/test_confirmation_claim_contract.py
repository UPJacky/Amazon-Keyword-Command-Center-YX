import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent
SQL = (ROOT / "migrations" / "010_claim_business_confirmation.sql").read_text(encoding="utf-8")
COMPACT = " ".join(SQL.lower().split())


class ConfirmationClaimContractTests(unittest.TestCase):
    def test_claim_returns_only_confirmed_bound_buyer_object(self):
        for fragment in (
            "business_confirmation",
            "c.object_id = 'buyer-checklist'",
            "c.version = v_task.confirmation_version",
            "c.store_id = v_task.store_id",
            "c.task_id = v_task.task_id",
            "c.self_asin = v_task.self_asin",
            "c.status = 'confirmed'",
        ):
            self.assertIn(fragment, COMPACT)

    def test_confirmation_object_kind_is_allowlisted_and_immutable(self):
        self.assertIn("p_object_id not in ('buyer-checklist', 'feature-review')", COMPACT)
        self.assertIn("confirmation_version_immutable", COMPACT)
        self.assertIn("confirmation_version_identity_immutable", COMPACT)
        self.assertIn("grant execute on function public.kwcc_claim_run(text, int) to service_role", COMPACT)


if __name__ == "__main__":
    unittest.main()
