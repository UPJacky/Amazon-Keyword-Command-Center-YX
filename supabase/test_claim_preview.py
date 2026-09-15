"""Offline contract checks for the read-only R12 claim preview migration."""

from __future__ import annotations

from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parent
RAW = (ROOT / "migrations" / "011_provider_claim_preview.sql").read_text(encoding="utf-8")
SQL = " ".join(re.sub(r"--[^\n]*", " ", RAW).lower().split())
RAW_ATOMIC = (ROOT / "migrations" / "012_claim_previewed_run_atomically.sql").read_text(encoding="utf-8")
SQL_ATOMIC = " ".join(re.sub(r"--[^\n]*", " ", RAW_ATOMIC).lower().split())


class ClaimPreviewStaticContract(unittest.TestCase):
    def test_preview_is_additive_transactional_and_read_only(self):
        self.assertTrue(SQL.startswith("begin;"))
        self.assertTrue(SQL.endswith("commit;"))
        self.assertIn("create or replace function public.kwcc_preview_next_run()", SQL)
        self.assertIn("returns jsonb language plpgsql security definer set search_path = ''", SQL)
        self.assertIn("auth.role() is distinct from 'service_role'", SQL)
        self.assertIn("where t.status = 'pending' and r.status = 'pending'", SQL)
        self.assertIn("order by r.created_at, r.run_id", SQL)
        self.assertIn("limit 1", SQL)
        self.assertIn("return null", SQL)
        self.assertNotRegex(SQL, r"\b(update|insert|delete|truncate|claim)\b")

    def test_preview_projection_is_minimal_and_has_worker_only_acl(self):
        for field in (
            "task_id", "store_id", "self_asin", "competitor_asins",
            "core_keywords", "primary_core_keyword", "marketplace", "run_id",
        ):
            self.assertIn("'" + field + "'", SQL)
        self.assertIn("revoke all on function public.kwcc_preview_next_run() from public, anon, authenticated, service_role", SQL)
        self.assertIn("grant execute on function public.kwcc_preview_next_run() to service_role", SQL)

    def test_previewed_claim_binds_identity_and_rolls_back_stale_claim(self):
        self.assertTrue(SQL_ATOMIC.startswith("begin;"))
        self.assertTrue(SQL_ATOMIC.endswith("commit;"))
        self.assertIn("create or replace function public.kwcc_claim_previewed_run(", SQL_ATOMIC)
        self.assertIn("p_worker_id text", SQL_ATOMIC)
        self.assertIn("p_lease_seconds int", SQL_ATOMIC)
        self.assertIn("p_task_id uuid", SQL_ATOMIC)
        self.assertIn("p_run_id uuid", SQL_ATOMIC)
        self.assertIn("for update of t, r", SQL_ATOMIC)
        self.assertIn("public.kwcc_claim_run(p_worker_id, p_lease_seconds)", SQL_ATOMIC)
        self.assertIn("errcode = 'p0001'", SQL_ATOMIC)
        self.assertIn("exception when sqlstate 'p0001'", SQL_ATOMIC)
        self.assertIn("preview_stale", SQL_ATOMIC)
        self.assertIn("grant execute on function public.kwcc_claim_previewed_run(text, int, uuid, uuid) to service_role", SQL_ATOMIC)


if __name__ == "__main__":
    unittest.main()
