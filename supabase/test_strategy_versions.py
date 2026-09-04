"""Offline SQL source contracts for 006, NOT executed PostgreSQL/RLS tests.

Run: python -B -m unittest discover -s supabase -p test_strategy_versions.py -v
These assertions detect missing guards/shape drift; database authorization,
transaction atomicity and concurrent replay still require database execution.
"""
from pathlib import Path
import ast
import json
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
RAW = (ROOT / 'supabase/migrations/006_strategy_versions.sql').read_text(encoding='utf-8')
SQL = re.sub(r'--[^\n]*', '', RAW)
COMPACT = ' '.join(SQL.lower().split())
FUNCTIONS = {
    match[1]: (match[2], match[3], match[4])
    for match in re.finditer(
        r'create or replace function public\.(kwcc_\w+)\((.*?)\)\s*returns (.*?) as \$\$(.*?)\$\$;',
        SQL, re.S | re.I,
    )
}
SHAPE = json.loads(re.search(r"v_shape constant jsonb := '(.*?)'::jsonb", SQL, re.S)[1])


def body(name):
    return ' '.join(FUNCTIONS['kwcc_' + name][2].lower().split())


class StrategyVersionsStaticContracts(unittest.TestCase):
    def test_rpc_signatures_and_search_paths(self):
        expected = {
            'kwcc_save_strategy': 'p_store_id uuid, p_product_stage text, p_config jsonb, p_config_version text, p_rule_version text, p_config_id uuid',
            'kwcc_rollback_strategy': 'p_config_id uuid, p_new_config_id uuid, p_config_version text',
        }
        self.assertEqual(len(FUNCTIONS), 4)
        for name, (args, declaration, _) in FUNCTIONS.items():
            self.assertIn("set search_path = ''", declaration)
            if name in expected:
                self.assertEqual(' '.join(args.split()), expected[name])
                self.assertIn('jsonb language plpgsql security definer', declaration)

    def test_acl_only_two_exposed_rpcs_no_direct_history_writes(self):
        signatures = {
            'kwcc_validate_strategy': 'text, jsonb, text, text',
            'kwcc_append_strategy': 'uuid, text, text, jsonb, text, text, uuid, uuid',
            'kwcc_save_strategy': 'uuid, text, jsonb, text, text, uuid',
            'kwcc_rollback_strategy': 'uuid, uuid, text',
        }
        for name, args in signatures.items():
            self.assertIn(f'revoke all on function public.{name}({args}) from public, anon, authenticated;', COMPACT)
        granted = re.findall(r'grant execute on function public\.(\w+)', COMPACT)
        self.assertEqual(granted, ['kwcc_save_strategy', 'kwcc_rollback_strategy'])
        self.assertIn('revoke insert, update, delete on public.strategy_configs from public, anon, authenticated;', COMPACT)

    def test_authorization_is_current_store_admin_before_read_or_replay(self):
        append = body('append_strategy')
        for guard in ('v_uid uuid := auth.uid()', 'v_uid is null', 'p_store_id is null',
                      'sm.store_id = p_store_id', 'sm.user_id = v_uid', "sm.role = 'admin'", "errcode = '42501'"):
            self.assertIn(guard, append)
        self.assertLess(append.index('strategy_admin_required'), append.index('where config_id = p_config_id'))
        self.assertIn('return public.kwcc_append_strategy(p_store_id, null, p_product_stage', body('save_strategy'))
        self.assertNotIn('public.profiles', COMPACT)
        self.assertNotIn('has_store_access', COMPACT)

    def test_default_configs_have_exactly_the_enumerated_numeric_fields(self):
        defaults = list((ROOT / 'rules/defaults').glob('*.json'))
        self.assertTrue(defaults)
        for path in defaults:
            with self.subTest(default=path.name):
                config = json.loads(path.read_text(encoding='utf-8'))
                self.assertEqual(config['schema_version'], 'config-0.1')
                self.assertEqual(set(config), {'schema_version', 'config_version', 'product_stage', *SHAPE})
                for section, fields in SHAPE.items():
                    self.assertEqual(set(config[section]), set(fields))
                    for name, (minimum, maximum, integer) in fields.items():
                        value = config[section][name]
                        self.assertNotIsInstance(value, bool)
                        self.assertGreaterEqual(value, minimum)
                        self.assertLessEqual(value, maximum)
                        if integer:
                            self.assertEqual(value, int(value))

    def test_shape_rejects_unknown_missing_null_string_boolean_numbers(self):
        code = body('validate_strategy')
        for marker in ("jsonb_typeof(p_config) is distinct from 'object'",
                       "jsonb_typeof(p_config->v_section) is distinct from 'object'",
                       "jsonb_typeof(p_config->v_section->v_name) is distinct from 'number'",
                       'where not (v_fields ? key)', 'p_config - array[',
                       'p_config->\'config_version\' is distinct from to_jsonb(p_config_version)',
                       'p_config->\'product_stage\' is distinct from to_jsonb(p_product_stage)'):
            self.assertIn(marker, code)
        self.assertLess(code.index("is distinct from 'number'"), code.index('::numeric'))
        self.assertIn("v_number::text in ('nan', 'infinity', '-infinity')", code)
        self.assertIn('v_number < (v_bounds->>0)::numeric or v_number > (v_bounds->>1)::numeric', code)
        self.assertIn('v_number <> trunc(v_number)', code)

    def test_all_order_relations_are_present(self):
        code = body('validate_strategy')
        for section, left, op, right in [
            ('acos', 'target', '>', 'tolerance'), ('acos', 'tolerance', '>', 'break_even'),
            ('evidence', 'insufficient_clicks_max', '>=', 'preliminary_clicks_min'),
            ('evidence', 'preliminary_clicks_min', '>', 'sufficient_clicks_min'),
            ('evidence', 'preliminary_orders_min', '>', 'sufficient_orders_min'),
        ]:
            self.assertIn(f"(p_config#>>'{{{section},{left}}}')::numeric {op} (p_config#>>'{{{section},{right}}}')::numeric", code)

    def test_rule_whitelist_matches_shipped_definitions_not_input_or_template_version(self):
        mapping = json.loads((ROOT / 'rules/action_mapping.json').read_text(encoding='utf-8'))
        module = ast.parse((ROOT / 'worker/report/generate_report.py').read_text(encoding='utf-8'))
        legacy = next(ast.literal_eval(n.value) for n in module.body if isinstance(n, ast.Assign)
                      and any(isinstance(t, ast.Name) and t.id == 'RULE_VERSION' for t in n.targets))
        allowed = set(re.findall(r"'([^']+)'", re.search(r'p_rule_version not in \((.*?)\)', SQL)[1]))
        self.assertEqual(allowed, {mapping['rule_version'], legacy})
        self.assertIn('p_rule_version is null', body('validate_strategy'))

    def test_idempotency_checks_full_content_before_return_and_audit_once(self):
        code = body('append_strategy')
        self.assertLess(code.index('pg_advisory_xact_lock'), code.index('where config_id = p_config_id'))
        for field in ('store_id', 'asin', 'product_stage', 'config_version', 'rule_version', 'config'):
            self.assertIn(f'v_row.{field} is distinct from p_{field}', code)
        self.assertIn("message = 'strategy_id_conflict'", code)
        self.assertLess(code.index('return to_jsonb(v_row)'), code.index('insert into public.strategy_configs'))
        self.assertEqual(code.count('insert into public.audit_events'), 1)
        self.assertIn("ae.metadata->>'source_config_id' = p_source_id::text", code)

    def test_append_only_scope_lock_and_strict_timestamp_order(self):
        self.assertNotRegex(COMPACT, r'\b(update|delete from|truncate|create table)\s+public\.')
        self.assertNotIn('on conflict', COMPACT)
        code = body('append_strategy')
        for fragment in ("'strategy-scope:' || p_store_id::text || ':' || p_product_stage",
                         "max(created_at) + interval '1 microsecond'", 'greatest(clock_timestamp()',
                         'where store_id = p_store_id and product_stage = p_product_stage',
                         'and config_version = p_config_version', "message = 'strategy_version_conflict'"):
            self.assertIn(fragment, code)
        self.assertTrue(COMPACT.startswith('begin;'))
        self.assertTrue(COMPACT.endswith('commit;'))

    def test_rollback_authorizes_source_and_copies_config_scope_and_rule(self):
        code = body('rollback_strategy')
        for fragment in ('if not found or v_uid is null or v_source.store_id is null',
                         'sm.store_id = v_source.store_id', 'sm.user_id = v_uid', "sm.role = 'admin'",
                         'p_new_config_id = p_config_id', 'p_config_version = v_source.config_version',
                         'public.kwcc_validate_strategy(v_source.product_stage, v_source.config,',
                         'public.kwcc_append_strategy(v_source.store_id, v_source.asin, v_source.product_stage,',
                         "jsonb_set(v_source.config, '{config_version}', to_jsonb(p_config_version), false)",
                         'p_config_version, v_source.rule_version, p_new_config_id, p_config_id'):
            self.assertIn(fragment, code)
        self.assertLess(code.index('strategy_admin_required'), code.index('return public.kwcc_append_strategy'))


if __name__ == '__main__':
    unittest.main()
