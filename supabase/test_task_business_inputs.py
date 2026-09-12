import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SQL = (ROOT / "supabase/migrations/007_task_business_inputs.sql").read_text(encoding="utf-8")
HARDENING = (ROOT / "supabase/migrations/009_confirmation_binding_hardening.sql").read_text(encoding="utf-8")
COMPACT = " ".join(SQL.lower().split())
HARDENING_COMPACT = " ".join(HARDENING.lower().split())


class TaskBusinessInputMigrationTests(unittest.TestCase):
    def test_additive_task_versions_and_confirmation_table(self):
        for field in ("primary_core_keyword", "competitor_selection_version", "product_facts_version", "feature_review_version", "checklist_version"):
            self.assertIn(f"add column if not exists {field}", COMPACT)
        self.assertIn("create table if not exists public.task_confirmations", COMPACT)
        self.assertIn("jsonb_typeof(items) = 'array'", COMPACT)

    def test_confirmation_is_authenticated_and_server_identity_is_used(self):
        self.assertIn("auth.uid()", COMPACT)
        self.assertIn("case when p_status = 'confirmed' then v_uid", COMPACT)
        self.assertIn("public.has_store_access(p_store_id)", COMPACT)
        self.assertIn("grant execute on function public.kwcc_save_task_confirmation", COMPACT)

    def test_confirmation_hash_and_status_are_validated(self):
        self.assertIn("p_input_hash !~ '^[0-9a-fa-f]{64}$'", COMPACT)
        self.assertIn("p_status not in ('draft', 'confirmed', 'rejected')", COMPACT)
        self.assertIn("p_status = 'confirmed' and p_task_id is null", COMPACT)

    def test_confirmation_is_bound_to_task_store_asin_and_confirmed_version_is_immutable(self):
        self.assertIn("v_task.store_id is distinct from p_store_id", HARDENING_COMPACT)
        self.assertIn("v_task.self_asin is distinct from p_self_asin", HARDENING_COMPACT)
        self.assertIn("confirmation_task_store_asin_mismatch", HARDENING_COMPACT)
        self.assertIn("confirmation_version_immutable", HARDENING_COMPACT)
        self.assertIn("confirmation_version_identity_immutable", HARDENING_COMPACT)
        self.assertIn("for update", HARDENING_COMPACT)
        self.assertIn("lower(p_input_hash)", HARDENING_COMPACT)


if __name__ == '__main__':
    unittest.main()
