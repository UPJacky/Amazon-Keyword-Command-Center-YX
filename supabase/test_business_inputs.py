import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent


class BusinessInputMigrationContracts(unittest.TestCase):
    def setUp(self):
        self.sql = (ROOT / "migrations" / "008_business_input_submission.sql").read_text(encoding="utf-8").lower()

    def test_wrapper_binds_business_fields_after_original_submission(self):
        self.assertIn("create or replace function public.kwcc_submit_task_with_business_inputs", self.sql)
        self.assertIn("p_business_inputs jsonb", self.sql)
        self.assertIn("v_result := public.kwcc_submit_task(", self.sql)
        self.assertIn("update public.tasks", self.sql)
        for field in ("primary_core_keyword", "competitor_asins", "core_keywords", "competitor_selection_version", "product_facts_version", "feature_review_version", "checklist_version", "confirmation_version"):
            self.assertIn(field, self.sql)

    def test_wrapper_rejects_invalid_asins_and_limits_arrays(self):
        self.assertIn("jsonb_array_length(v_competitors) > 5", self.sql)
        self.assertIn("jsonb_array_length(v_keywords) > 200", self.sql)
        self.assertIn("v_item !~ '^b0[a-z0-9]{8}$'", self.sql)
        self.assertIn("group by value having count(*) > 1", self.sql)

    def test_privilege_is_authenticated_only(self):
        self.assertIn("revoke all on function public.kwcc_submit_task_with_business_inputs", self.sql)
        self.assertIn("from public, anon, authenticated, service_role", self.sql)
        self.assertIn("to authenticated", self.sql)


if __name__ == "__main__":
    unittest.main()
