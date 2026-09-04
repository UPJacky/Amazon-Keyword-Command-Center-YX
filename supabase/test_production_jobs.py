"""Offline static contract checks for 005; never a PostgreSQL/RLS execution test.

Run: python -B -m unittest discover -s supabase -p test_production_jobs.py -v
Only reads the migration. Optional pglast parses SQL grammar, not runtime behavior.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
import re
import unittest

try:
    from .migration_contract_check import _normalised_statements
except ImportError:
    from migration_contract_check import _normalised_statements


ROOT = Path(__file__).resolve().parent
RAW = (ROOT / "migrations" / "005_production_jobs.sql").read_text(encoding="utf-8")
# This file contains no comment markers inside literals. Drop comments before
# assertions so comments describing a guard cannot substitute for its SQL.
SQL = re.sub(r"--[^\n]*", "", RAW)
STATEMENTS = _normalised_statements(SQL)


def compact(text: str) -> str:
    return " ".join(text.lower().split())


FUNCTIONS = {
    m.group(1): (compact(m.group(2)), compact(m.group(3)), compact(m.group(4)))
    for m in re.finditer(
        r"create or replace function public\.(kwcc_\w+)\((.*?)\)\s*"
        r"returns (.*?) as \$\$(.*?)\$\$;", SQL, re.S | re.I
    )
}
ACL_SIGNATURES = {
    "kwcc_submit_task": "uuid, uuid, uuid, text, text, text, text, bigint, uuid",
    "kwcc_rerun_task": "uuid, uuid, uuid",
    "kwcc_claim_run": "text, int",
    "kwcc_heartbeat_run": "uuid, uuid, int",
    "kwcc_finish_run": "uuid, uuid, text, text, text, text, text, jsonb",
}


def body(name: str) -> str:
    return FUNCTIONS["kwcc_" + name][2]


def policy(name: str) -> str:
    return next(s for s in STATEMENTS if s.startswith(f"create policy {name} "))


class ProductionJobsStaticContract(unittest.TestCase):
    def assertContains(self, text: str, *clauses: str) -> None:
        for clause in clauses:
            with self.subTest(clause=clause):
                self.assertIn(compact(clause), text)

    def test_single_transaction_repeatable_owned_ddl(self):
        self.assertEqual(STATEMENTS[0], "begin")
        self.assertEqual(STATEMENTS[-1], "commit")
        self.assertEqual(STATEMENTS.count("begin"), 1)
        self.assertEqual(STATEMENTS.count("commit"), 1)
        for statement in STATEMENTS:
            if statement.startswith("alter table"):
                self.assertIn("add column if not exists", statement)
            if statement.startswith("create ") and " index " in statement:
                self.assertIn("index if not exists kwcc_", statement)
            if statement.startswith("drop policy"):
                self.assertRegex(statement, r"^drop policy if exists kwcc_\w+ on storage.objects$")
        self.assertNotRegex(compact(SQL), r"\b(drop table|truncate|delete from)\b")

    def test_exact_function_signatures_and_defaults(self):
        expected = {
            "kwcc_submit_task": "p_task_id uuid, p_run_id uuid, p_store_id uuid, p_self_asin text, p_product_stage text, p_input_file_path text, p_input_file_hash text, p_input_size bigint, p_strategy_id uuid default null",
            "kwcc_rerun_task": "p_task_id uuid, p_previous_run_id uuid, p_run_id uuid",
            "kwcc_claim_run": "p_worker_id text, p_lease_seconds int default 300",
            "kwcc_heartbeat_run": "p_run_id uuid, p_lease_token uuid, p_lease_seconds int default 300",
            "kwcc_finish_run": "p_run_id uuid, p_lease_token uuid, p_status text, p_report_path text default null, p_rule_version text default null, p_config_version text default null, p_provider_snapshot_version text default null, p_failure_reason jsonb default null",
        }
        self.assertEqual(set(FUNCTIONS), set(expected))
        for name, parameters in expected.items():
            self.assertEqual(FUNCTIONS[name][0], parameters)
            result_type = "boolean" if name in ("kwcc_heartbeat_run", "kwcc_finish_run") else "jsonb"
            self.assertEqual(FUNCTIONS[name][1], result_type + " language plpgsql security definer set search_path = ''")

    def test_function_execute_acl_is_exact_and_worker_is_not_authenticated(self):
        grants = [s for s in STATEMENTS if s.startswith("grant execute ")]
        self.assertEqual(len(grants), 5)
        for name, signature in ACL_SIGNATURES.items():
            role = "authenticated" if name in ("kwcc_submit_task", "kwcc_rerun_task") else "service_role"
            grant = f"grant execute on function public.{name}({signature}) to {role}"
            revoke = f"revoke all on function public.{name}({signature}) from public, anon, authenticated, service_role"
            self.assertIn(grant, STATEMENTS)
            self.assertIn(revoke, STATEMENTS)
            self.assertLess(STATEMENTS.index(revoke), STATEMENTS.index(grant))
            if role == "service_role":
                self.assertIn("auth.role() is distinct from 'service_role'", FUNCTIONS[name][2])

    def test_revoke_table_and_all_historical_column_insert_grants(self):
        self.assertIn("revoke insert on table public.tasks from public, anon, authenticated", STATEMENTS)
        old = (ROOT / "migrations" / "003_authenticated_only.sql").read_text(encoding="utf-8")
        old_columns = re.search(r"grant insert\s*\((.*?)\) on table public.tasks", old, re.S).group(1)
        revoked = next(s for s in STATEMENTS if s.startswith("revoke insert ("))
        new_columns = re.search(r"revoke insert \((.*?)\) on table public.tasks", revoked).group(1)
        self.assertEqual({c.strip() for c in old_columns.split(",")}, {c.strip() for c in new_columns.split(",")})
        self.assertIn("from public, anon, authenticated", revoked)
        self.assertNotRegex(compact(SQL), r"grant (?:all|insert|update|delete).*?on table")

    def test_inputs_bucket_private_limit_and_repeatable_upsert(self):
        bucket = next(s for s in STATEMENTS if s.startswith("insert into storage.buckets"))
        self.assertContains(bucket, "'inputs', 'inputs', false, 10485760", "on conflict (id) do update set public = false", "file_size_limit = excluded.file_size_limit")
        self.assertContains(policy("kwcc_inputs_insert"), "for insert to authenticated", "with check (bucket_id = 'inputs')")

    def test_insert_guard_binds_owner_membership_and_canonical_path(self):
        guard = policy("kwcc_objects_insert_guard")
        self.assertContains(guard, "as restrictive for insert to authenticated", "bucket_id <> 'reports'", "bucket_id <> 'inputs' or", "(select auth.uid()) is not null", "owner_id = (select auth.uid())::text", "split_part(name, '/', 2) = (select auth.uid())::text", "sm.store_id::text = split_part(name, '/', 1)", "sm.user_id = (select auth.uid())", "public.has_store_access(sm.store_id)")
        # Untrusted path components are compared as text, never cast to UUID.
        self.assertNotRegex(guard, r"split_part\([^)]*\)::uuid")

    def test_input_path_regex_positive_and_negative_examples(self):
        expression = re.search(r"name ~ '([^']+)'", policy("kwcc_objects_insert_guard")).group(1)
        prefix = "/".join(["00000000-0000-4000-8000-000000000001"] * 3)
        for suffix in ("xlsx", "csv"):
            self.assertIsNotNone(re.fullmatch(expression, prefix + "/input." + suffix))
        for name in (prefix + "/input.csv/extra", prefix + "/input.csv\n", prefix + "/other.xlsx", prefix + "/input.exe", prefix + "/input.XLSX", prefix + "/../input.csv", prefix + "/input%2exlsx", "../" + prefix + "/input.csv", prefix.replace("/", "\\") + "\\input.csv"):
            with self.subTest(path=name):
                self.assertIsNone(re.fullmatch(expression, name))

    def test_no_user_overwrite_delete_or_report_write_and_old_report_read_untouched(self):
        for operation in ("update", "delete"):
            guard = policy("kwcc_objects_" + operation + "_guard")
            self.assertContains(guard, f"as restrictive for {operation} to anon, authenticated", "using (bucket_id not in ('inputs', 'reports'))")
        self.assertIn("with check (bucket_id not in ('inputs', 'reports'))", policy("kwcc_objects_update_guard"))
        self.assertIn("for insert to anon with check (bucket_id not in ('inputs', 'reports'))", policy("kwcc_objects_anon_insert_guard"))
        self.assertNotIn("reports_member_read", compact(SQL))
        self.assertFalse(any(s.startswith("create policy") and "for select" in s for s in STATEMENTS))

    def test_submit_auth_validation_and_null_rejection(self):
        submit = body("submit_task")
        self.assertContains(submit, "v_uid uuid := auth.uid()", "v_uid is null or p_store_id is null", "not public.has_store_access(p_store_id)", "p_task_id is null or p_run_id is null", "p_input_size is null or p_input_size < 1 or p_input_size > 10485760", "p_self_asin is null", "p_product_stage is null", "p_input_file_hash is null", "p_input_file_path is null", "p_product_stage not in ('new', 'growth', 'stable', 'clearance', 'seasonal_restart')")

    def test_submit_hash_syntax_only_and_exact_object_metadata(self):
        submit = body("submit_task")
        self.assertContains(submit, "p_input_file_hash !~ '^[0-9a-f]{64}$'", "p_store_id::text || '/' || v_uid::text || '/' || p_task_id::text || '/input.'", "p_input_file_path not in (v_prefix || 'xlsx', v_prefix || 'csv')", "o.bucket_id = 'inputs' and b.public = false", "o.name = p_input_file_path and o.owner_id = v_uid::text", "o.metadata ->> 'size'", "for share of o", "v_size is null or v_size !~ '^[0-9]{1,8}$'", "v_size::bigint <> p_input_size")
        self.assertLess(submit.index("v_size !~"), submit.index("v_size::bigint"))
        self.assertLess(submit.index("v_size::bigint"), submit.index("insert into public.tasks"))
        self.assertIn("recompute SHA-256 before any Provider call", RAW)

    def test_strategy_is_scoped_to_store_asin_and_stage(self):
        self.assertContains(body("submit_task"), "s.config_id = p_strategy_id", "s.store_id = p_store_id", "s.asin is null or s.asin = p_self_asin", "s.product_stage is null or s.product_stage = p_product_stage")

    def test_omitted_strategy_selects_latest_matching_asin_before_store_default(self):
        submit = body("submit_task")
        self.assertContains(submit, "if p_strategy_id is null then", "select s.config_id into v_strategy_id", "s.store_id = p_store_id and s.product_stage = p_product_stage", "s.asin = p_self_asin or s.asin is null", "order by (s.asin = p_self_asin) desc nulls last, s.created_at desc, s.config_id desc limit 1", "strategy_id, requested_strategy_id, input_file_path", "v_strategy_id, p_strategy_id, p_input_file_path")
        self.assertLess(submit.index("if p_strategy_id is null then"), submit.index("insert into public.tasks"))
        self.assertNotIn("strategy_heads", compact(SQL))
        self.assertNotIn("006", compact(SQL))

    def test_submit_exact_replay_fences_every_request_field(self):
        submit = body("submit_task")
        self.assertIn("pg_catalog.pg_advisory_xact_lock", submit)
        self.assertIn("where task_id = p_task_id for update", submit)
        self.assertIn("run_id = p_run_id and task_id = p_task_id and previous_run_id is null", submit)
        for field in ("store_id", "self_asin", "product_stage", "input_file_path", "input_file_hash", "input_size"):
            self.assertIn(f"v_task.{field} is distinct from p_{field}", submit)
        self.assertIn("v_task.requested_strategy_id is distinct from p_strategy_id", submit)
        self.assertIn("v_task.created_by is distinct from v_uid", submit)
        self.assertContains(submit, "'run_id', v_run.run_id, 'status', 'pending'", "exception when unique_violation then", "message = 'job_id_conflict'")
        self.assertLess(submit.index("'run_id', v_run.run_id, 'status', 'pending'"), submit.index("if p_strategy_id is null then"))

    def test_task_run_and_audit_are_one_atomic_submission(self):
        submit = body("submit_task")
        positions = [submit.index("insert into public." + table) for table in ("tasks", "task_runs", "audit_events")]
        self.assertEqual(positions, sorted(positions))
        for name in FUNCTIONS:
            self.assertNotRegex(FUNCTIONS[name][2], r"\b(commit|rollback)\b")
        self.assertIn("'task_submitted'", submit)

    def test_lease_columns_and_unique_active_and_successor_indexes(self):
        self.assertContains(compact(SQL), "add column if not exists lease_token uuid", "add column if not exists worker_id text", "add column if not exists lease_until timestamptz", "add column if not exists failure_reason jsonb", "on public.task_runs(task_id) where status in ('pending', 'processing')", "on public.task_runs(previous_run_id) where previous_run_id is not null")

    def test_claim_skip_locked_expiry_fails_without_requeue(self):
        claim = body("claim_run")
        self.assertEqual(claim.count("for update of t, r skip locked"), 2)
        self.assertContains(claim, "r.lease_until is null or r.lease_until <= clock_timestamp()", "update public.task_runs set status = 'failed'", "update public.tasks set status = 'failed'", "'run_lease_expired'", '"code":"lease_expired"', '"retryable":false')
        self.assertNotIn("set status = 'pending'", claim)
        self.assertLess(claim.index("'run_lease_expired'"), claim.index("if not found then return null"))

    def test_claim_response_and_random_lease_with_bounded_ttl(self):
        claim = body("claim_run")
        self.assertContains(claim, "where t.status = 'pending' and r.status = 'pending'", "limit 1 for update", "lease_token = gen_random_uuid()", "worker_id = p_worker_id", "lease_until = v_now + make_interval(secs => p_lease_seconds)", "p_lease_seconds is null or p_lease_seconds < 1 or p_lease_seconds > 3600", "select s.config into v_config", "s.store_id = v_task.store_id", "'task', to_jsonb(v_task) || jsonb_build_object(", "'marketplace', (select s.marketplace from public.stores s where s.store_id = v_task.store_id)", "'run', to_jsonb(v_run), 'config', v_config", "'run_claimed'")

    def test_heartbeat_cannot_resurrect_or_shorten_lease(self):
        beat = body("heartbeat_run")
        self.assertContains(beat, "where run_id = p_run_id for update", "p_lease_token is null", "v_run.lease_token is distinct from p_lease_token", "v_run.status <> 'processing'", "v_run.lease_until is null", "v_run.lease_until <= v_now then return false", "set lease_until = greatest(lease_until", "where run_id = p_run_id and lease_token = p_lease_token", "status = 'processing' and lease_until > v_now", "return found")
        self.assertLess(beat.index("for update"), beat.index("v_now := clock_timestamp()"))

    def test_finish_cas_after_report_lock_and_terminal_only(self):
        finish = body("finish_run")
        self.assertContains(finish, "p_status is null or p_status not in ('completed', 'failed')", "v_run.lease_token is distinct from p_lease_token", "v_run.lease_until <= v_now then return false", "where run_id = p_run_id and lease_token = p_lease_token", "status = 'processing' and lease_until > v_now", "if not found then return false", "'run_finished'")
        self.assertLess(finish.index("for update of t"), finish.index("where run_id = p_run_id for update"))
        self.assertLess(finish.index("for share of o"), finish.rindex("v_now := clock_timestamp()"))
        self.assertLess(finish.index("update public.task_runs"), finish.index("update public.tasks"))

    def test_completed_report_is_private_existing_exact_task_run_and_random_name(self):
        finish = body("finish_run")
        self.assertContains(finish, "p_failure_reason is not null or p_report_path is null", "'^' || v_task.task_id::text || '/' || p_run_id::text || '/report-[0-9a-f]{48}\\.json$'", "o.bucket_id = 'reports' and b.public = false and o.name = p_report_path", "for share of o", "message = 'report_object_missing'")
        expression = re.search(r"'(/report-[^']+)'", finish).group(1)
        self.assertIsNotNone(re.fullmatch(expression, "/report-" + "ab" * 24 + ".json"))
        for name in ("/master-table.json", "/report-" + "a" * 47 + ".json", "/report-" + "g" * 48 + ".json", "/report-" + "a" * 48 + ".json/extra"):
            self.assertIsNone(re.fullmatch(expression, name))

    def test_failure_reason_rejects_arbitrary_data_and_is_rebuilt(self):
        finish = body("finish_run")
        self.assertContains(finish, "jsonb_typeof(p_failure_reason) is distinct from 'object'", "p_failure_reason ?& array['code', 'stage', 'retryable']", "(p_failure_reason - array['code', 'stage', 'retryable']) <> '{}'::jsonb", "jsonb_typeof(p_failure_reason -> 'code') is distinct from 'string'", "jsonb_typeof(p_failure_reason -> 'stage') is distinct from 'string'", "(p_failure_reason -> 'retryable') is distinct from 'false'::jsonb", "(p_failure_reason ->> 'code') not in", "(p_failure_reason ->> 'stage') not in", "v_reason := jsonb_build_object", "failure_reason = v_reason", "coalesce(v_reason, '{}'::jsonb)")
        self.assertNotIn("sqlerrm", compact(SQL))
        self.assertNotIn("metadata = p_failure_reason", finish)

    def test_rerun_terminal_member_and_same_task_previous_link(self):
        rerun = body("rerun_task")
        self.assertContains(rerun, "v_uid is null", "not public.has_store_access(v_task.store_id)", "where task_id = p_task_id for update", "where run_id = p_previous_run_id and task_id = p_task_id for update", "v_previous.status not in ('completed', 'failed')", "v_task.status not in ('completed', 'failed')", "v_task.input_size is null", "status in ('pending', 'processing')", "where previous_run_id = p_previous_run_id", "insert into public.task_runs(run_id, task_id, previous_run_id, strategy_id, status)", "'task_rerun_submitted'")
        self.assertNotIn("update public.task_runs", rerun)

    def test_operational_lease_fields_are_not_granted_to_members(self):
        self.assertIn("revoke select on table public.task_runs from authenticated", STATEMENTS)
        grant = next(s for s in STATEMENTS if s.startswith("grant select (") and "public.task_runs" in s)
        for private in ("lease_token", "worker_id", "lease_until"):
            self.assertNotIn(private, grant)
        self.assertContains(grant, "failure_reason", "strategy_id", "report_path", "to authenticated")

    def test_each_run_freezes_strategy_and_rerun_selects_current_version(self):
        self.assertContains(body("claim_run"), "s.config_id = v_run.strategy_id")
        self.assertContains(body("submit_task"), "insert into public.task_runs(run_id, task_id, strategy_id, status)")
        rerun = body("rerun_task")
        self.assertContains(rerun, "select s.config_id into v_strategy_id", "s.store_id = v_task.store_id", "s.product_stage = v_task.product_stage", "s.asin = v_task.self_asin or s.asin is null")
        self.assertLess(rerun.index("return jsonb_build_object"), rerun.index("select s.config_id into v_strategy_id"))

    def test_rerun_exact_replay_or_conflict_without_extra_audit(self):
        rerun = body("rerun_task")
        self.assertContains(rerun, "p_run_id = p_previous_run_id", "v_existing.task_id is distinct from p_task_id", "v_existing.previous_run_id is distinct from p_previous_run_id", "exception when unique_violation then")
        self.assertLess(rerun.index("return jsonb_build_object"), rerun.index("insert into public.task_runs"))

    def test_submission_and_rerun_responses_are_stable_pending_acknowledgements(self):
        for name in ("submit_task", "rerun_task"):
            returns = re.findall(r"return jsonb_build_object\(([^;]+)\);", body(name))
            self.assertEqual(len(returns), 2)
            for response in returns:
                self.assertRegex(response, r"^'task_id', [\w.]+, 'run_id', [\w.]+, 'status', 'pending'$")

    def test_documentation_does_not_claim_database_or_remote_validation(self):
        doc = (ROOT / "PRODUCTION_JOBS_REVIEW.md").read_text(encoding="utf-8")
        for marker in ("未应用", "静态合同", "PostgreSQL", "重新计算 SHA-256", "生产部署", "owner_id", "message"):
            self.assertIn(marker, doc)

    @unittest.skipUnless(importlib.util.find_spec("pglast"), "pglast unavailable; no install/network; SQL grammar NOT verified")
    def test_optional_local_postgresql_grammar_parser(self):
        import pglast
        self.assertTrue(pglast.parse_sql(RAW))
        # parse_sql treats PL/pgSQL bodies as strings; use its procedural parser
        # too when available. Neither parser executes the migration or RLS.
        if hasattr(pglast, "parse_plpgsql"):
            for match in re.finditer(r"create or replace function .*?\$\$;", SQL, re.S | re.I):
                self.assertTrue(pglast.parse_plpgsql(match.group(0)))


if __name__ == "__main__":
    unittest.main(verbosity=2)
