import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import supabase.migration_contract_check as contract


class MigrationContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.hardening_text = contract.HARDENING_MIGRATION.read_text(encoding="utf-8")

    def _check_hardening_text(self, text):
        with tempfile.TemporaryDirectory() as temp_dir:
            migration = Path(temp_dir) / "003_authenticated_only.sql"
            migration.write_text(text, encoding="utf-8")
            with patch.object(contract, "HARDENING_MIGRATION", migration):
                return contract.check()

    def _policy_block(self, name):
        start = self.hardening_text.index(f"create policy {name}\n")
        end = self.hardening_text.index(";", start) + 1
        return start, end, self.hardening_text[start:end]

    def _mutate_policy(self, name, old, new):
        start, end, block = self._policy_block(name)
        mutated_block = block.replace(old, new, 1)
        self.assertNotEqual(mutated_block, block)
        return self.hardening_text[:start] + mutated_block + self.hardening_text[end:]

    def assertProblemContains(self, problems, expected):
        self.assertTrue(
            any(expected in problem for problem in problems),
            f"expected a problem containing {expected!r}, got {problems!r}",
        )

    def test_reviewed_migrations_keep_private_authenticated_rls_contract(self):
        self.assertEqual(contract.check(), [])

    def test_seven_tables_eight_policies_and_insert_columns_are_locked(self):
        self.assertEqual(
            contract.MINIMUM_TABLE_PRIVILEGES,
            {
                "public.profiles": frozenset({"select"}),
                "public.stores": frozenset({"select"}),
                "public.store_memberships": frozenset({"select"}),
                "public.strategy_configs": frozenset({"select"}),
                "public.tasks": frozenset({"select"}),
                "public.task_runs": frozenset({"select"}),
                "public.audit_events": frozenset({"select"}),
            },
        )
        self.assertEqual(
            contract.TASK_INSERT_COLUMNS,
            frozenset(
                {
                    "task_id",
                    "created_by",
                    "store_id",
                    "self_asin",
                    "competitor_asins",
                    "core_keywords",
                    "product_stage",
                    "strategy_id",
                    "task_config_override",
                    "input_file_path",
                    "input_file_hash",
                    "currency_code",
                    "status",
                    "current_stage",
                }
            ),
        )
        self.assertEqual(
            contract.POLICY_TABLES,
            {
                "profiles_self": "public.profiles",
                "stores_member_read": "public.stores",
                "memberships_self_read": "public.store_memberships",
                "strategies_member_read": "public.strategy_configs",
                "tasks_member_read": "public.tasks",
                "tasks_member_insert": "public.tasks",
                "runs_member_read": "public.task_runs",
                "audit_member_read": "public.audit_events",
            },
        )

    def test_index_migration_is_part_of_the_reviewed_contract(self):
        self.assertTrue(contract.INDEX_MIGRATION.is_file())
        text = contract.INDEX_MIGRATION.read_text(encoding="utf-8").lower()
        for snippet in contract.REQUIRED_INDEX_SNIPPETS:
            self.assertIn(snippet.lower(), text)

    def test_hardening_migration_is_required(self):
        missing = contract.HARDENING_MIGRATION.with_name(
            "missing_authenticated_only.sql"
        )
        with patch.object(contract, "HARDENING_MIGRATION", missing):
            self.assertProblemContains(
                contract.check(), "missing 003_authenticated_only.sql"
            )

    def test_hardening_migration_reenables_rls_for_every_table(self):
        mutated = self.hardening_text.replace(
            "alter table public.audit_events enable row level security;\n",
            "",
            1,
        )
        self.assertNotEqual(mutated, self.hardening_text)
        self.assertProblemContains(
            self._check_hardening_text(mutated),
            "must enable RLS exactly once: public.audit_events",
        )

    def test_every_business_table_is_revoked_from_all_client_roles(self):
        role_mutations = {
            "public": "from anon, authenticated;",
            "anon": "from public, authenticated;",
            "authenticated": "from public, anon;",
        }
        for missing_role, replacement in role_mutations.items():
            with self.subTest(missing_role=missing_role):
                mutated = self.hardening_text.replace(
                    "from public, anon, authenticated;",
                    replacement,
                    1,
                )
                self.assertNotEqual(mutated, self.hardening_text)
                expected = (
                    f"revoke all table privileges from {missing_role}: public.profiles"
                    if missing_role != "authenticated"
                    else "reset authenticated table privileges: public.profiles"
                )
                self.assertProblemContains(
                    self._check_hardening_text(mutated), expected
                )

    def test_revoke_must_cover_all_seven_tables(self):
        mutated = self.hardening_text.replace(
            "  public.task_runs,\n  public.audit_events\n"
            "from public, anon, authenticated;",
            "  public.task_runs\nfrom public, anon, authenticated;",
            1,
        )
        self.assertNotEqual(mutated, self.hardening_text)
        problems = self._check_hardening_text(mutated)
        for role in ("public", "anon"):
            self.assertProblemContains(
                problems,
                f"revoke all table privileges from {role}: public.audit_events",
            )

    def test_authenticated_select_must_cover_all_seven_tables(self):
        mutated = self.hardening_text.replace(
            "  public.task_runs,\n  public.audit_events\nto authenticated;",
            "  public.task_runs\nto authenticated;",
            1,
        )
        self.assertNotEqual(mutated, self.hardening_text)
        self.assertProblemContains(
            self._check_hardening_text(mutated),
            "authenticated privileges mismatch for public.audit_events",
        )

    def test_authenticated_table_permissions_must_remain_select_only(self):
        mutated = self.hardening_text.replace(
            "grant select on table",
            "grant select, update on table",
            1,
        )
        self.assertNotEqual(mutated, self.hardening_text)
        self.assertProblemContains(
            self._check_hardening_text(mutated),
            "authenticated privileges mismatch for public.tasks",
        )

    def test_tasks_insert_columns_must_match_the_allowlist(self):
        mutated = self.hardening_text.replace(
            "  currency_code,\n  status,\n  current_stage",
            "  currency_code,\n  current_stage",
            1,
        )
        self.assertNotEqual(mutated, self.hardening_text)
        self.assertProblemContains(
            self._check_hardening_text(mutated),
            "tasks insert columns mismatch",
        )

    def test_table_wide_tasks_insert_is_rejected(self):
        mutated, substitutions = re.subn(
            r"grant insert \(.*?\) on table public\.tasks to authenticated;",
            "grant insert on table public.tasks to authenticated;",
            self.hardening_text,
            count=1,
            flags=re.DOTALL,
        )
        self.assertEqual(substitutions, 1)
        problems = self._check_hardening_text(mutated)
        self.assertProblemContains(
            problems, "authenticated privileges mismatch for public.tasks"
        )
        self.assertProblemContains(problems, "tasks insert columns mismatch")

    def test_public_or_anon_table_grant_is_rejected(self):
        for role in ("public", "anon"):
            with self.subTest(role=role):
                mutated = self.hardening_text.replace(
                    "grant select on table",
                    f"grant select on table public.audit_events to {role};\n\n"
                    "grant select on table",
                    1,
                )
                self.assertNotEqual(mutated, self.hardening_text)
                self.assertProblemContains(
                    self._check_hardening_text(mutated),
                    "grants a public role on public.audit_events",
                )

    def test_authenticated_schema_usage_is_required(self):
        mutated = self.hardening_text.replace(
            "grant usage on schema public to authenticated;\n",
            "",
            1,
        )
        self.assertNotEqual(mutated, self.hardening_text)
        self.assertProblemContains(
            self._check_hardening_text(mutated),
            "must grant only schema usage to authenticated",
        )

    def test_has_store_access_must_revoke_all_client_roles(self):
        source = (
            "revoke execute on function public.has_store_access(uuid) "
            "from public, anon, authenticated;"
        )
        role_mutations = {
            "public": "from anon, authenticated;",
            "anon": "from public, authenticated;",
            "authenticated": "from public, anon;",
        }
        for missing_role, role_clause in role_mutations.items():
            with self.subTest(missing_role=missing_role):
                mutated = self.hardening_text.replace(
                    source,
                    "revoke execute on function public.has_store_access(uuid) "
                    + role_clause,
                    1,
                )
                self.assertNotEqual(mutated, self.hardening_text)
                self.assertProblemContains(
                    self._check_hardening_text(mutated),
                    f"has_store_access must revoke execute from {missing_role}",
                )

    def test_has_store_access_execute_grant_is_authenticated_only(self):
        mutated = self.hardening_text.replace(
            "grant execute on function public.has_store_access(uuid) "
            "to authenticated;",
            "grant execute on function public.has_store_access(uuid) "
            "to authenticated, anon;",
            1,
        )
        self.assertNotEqual(mutated, self.hardening_text)
        self.assertProblemContains(
            self._check_hardening_text(mutated),
            "execute must be granted only to authenticated",
        )

    def test_has_store_access_requires_an_authenticated_user(self):
        mutated = self.hardening_text.replace(
            "    (select auth.uid()) is not null\n    and exists (",
            "    exists (",
            1,
        )
        self.assertNotEqual(mutated, self.hardening_text)
        self.assertProblemContains(
            self._check_hardening_text(mutated),
            "has_store_access must require a non-null auth.uid()",
        )

    def test_each_existing_policy_must_be_dropped_and_recreated(self):
        without_drop = self.hardening_text.replace(
            "drop policy if exists tasks_member_insert on public.tasks;\n",
            "",
            1,
        )
        self.assertNotEqual(without_drop, self.hardening_text)
        self.assertProblemContains(
            self._check_hardening_text(without_drop),
            "must drop policy exactly once: tasks_member_insert on public.tasks",
        )

        start, end, _ = self._policy_block("profiles_self")
        without_create = self.hardening_text[:start] + self.hardening_text[end:]
        self.assertProblemContains(
            self._check_hardening_text(without_create),
            "must recreate policy exactly once: profiles_self on public.profiles",
        )

    def test_all_eight_policies_are_authenticated_only(self):
        for name in contract.POLICY_TABLES:
            with self.subTest(policy=name):
                mutated = self._mutate_policy(
                    name,
                    "to authenticated\n",
                    "",
                )
                self.assertProblemContains(
                    self._check_hardening_text(mutated),
                    f"policy must target authenticated only: {name}",
                )

    def test_all_eight_policies_require_non_null_auth_uid(self):
        for name in contract.POLICY_TABLES:
            with self.subTest(policy=name):
                mutated = self._mutate_policy(
                    name,
                    "  (select auth.uid()) is not null\n  and ",
                    "  ",
                )
                self.assertProblemContains(
                    self._check_hardening_text(mutated),
                    f"policy must require a non-null auth.uid(): {name}",
                )

    def test_tasks_insert_requires_fixed_initial_status_and_stage(self):
        for guard, expected in (
            ("  and status = 'pending'\n", "must require status = 'pending'"),
            (
                "  and current_stage = 'ingestion'\n",
                "must require current_stage = 'ingestion'",
            ),
        ):
            with self.subTest(guard=guard):
                mutated = self._mutate_policy(
                    "tasks_member_insert",
                    guard,
                    "",
                )
                self.assertProblemContains(
                    self._check_hardening_text(mutated), expected
                )

    def test_null_store_audit_events_are_limited_to_the_same_user(self):
        mutated = self._mutate_policy(
            "audit_member_read",
            "store_id is null and user_id = (select auth.uid())",
            "store_id is null",
        )
        self.assertProblemContains(
            self._check_hardening_text(mutated),
            "limit null-store events to user_id = auth.uid()",
        )


if __name__ == "__main__":
    unittest.main()
