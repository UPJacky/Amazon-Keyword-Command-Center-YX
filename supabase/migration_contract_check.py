"""Static checks for the reviewed Supabase migration contract.

This does not execute SQL. It catches accidental removal of RLS, private
report-read policies, and the authenticated-only hardening before migrations
are run in a disposable project.
"""

from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parent
MIGRATION = ROOT / "migrations" / "001_initial_schema.sql"
INDEX_MIGRATION = ROOT / "migrations" / "002_indexes.sql"
HARDENING_MIGRATION = ROOT / "migrations" / "003_authenticated_only.sql"


REQUIRED_SNIPPETS = (
    # Every user-visible table must remain behind RLS. Worker writes use a
    # reviewed server-side role; absence of a public write policy is
    # intentional and must not be weakened by a future migration edit.
    "alter table public.profiles enable row level security",
    "alter table public.stores enable row level security",
    "alter table public.store_memberships enable row level security",
    "alter table public.strategy_configs enable row level security",
    "alter table public.tasks enable row level security",
    "alter table public.task_runs enable row level security",
    "alter table public.audit_events enable row level security",
    "create policy tasks_member_read",
    "create policy runs_member_read",
    "public.has_store_access(t.store_id)",
    "report_path text",
)

REQUIRED_INDEX_SNIPPETS = (
    "create index if not exists idx_store_memberships_user on public.store_memberships(user_id)",
    "create index if not exists idx_tasks_store_created on public.tasks(store_id, created_at desc)",
    "create index if not exists idx_tasks_status_created on public.tasks(status, created_at)",
    "create index if not exists idx_task_runs_task_created on public.task_runs(task_id, created_at desc)",
    "create index if not exists idx_audit_events_store_created on public.audit_events(store_id, created_at desc)",
)

FORBIDDEN_SNIPPETS = (
    # A report path is metadata only. Public buckets/policies would bypass
    # the authenticated task/run read path and are not part of V1.
    "create policy report_public_read",
    "create policy storage_public_read",
    "using (true)",
)

MINIMUM_TABLE_PRIVILEGES = {
    "public.profiles": frozenset({"select"}),
    "public.stores": frozenset({"select"}),
    "public.store_memberships": frozenset({"select"}),
    "public.strategy_configs": frozenset({"select"}),
    "public.tasks": frozenset({"select"}),
    "public.task_runs": frozenset({"select"}),
    "public.audit_events": frozenset({"select"}),
}

TASK_INSERT_COLUMNS = frozenset(
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
)

POLICY_TABLES = {
    "profiles_self": "public.profiles",
    "stores_member_read": "public.stores",
    "memberships_self_read": "public.store_memberships",
    "strategies_member_read": "public.strategy_configs",
    "tasks_member_read": "public.tasks",
    "tasks_member_insert": "public.tasks",
    "runs_member_read": "public.task_runs",
    "audit_member_read": "public.audit_events",
}

_DOLLAR_QUOTE = re.compile(r"\$[A-Za-z_][A-Za-z0-9_]*\$|\$\$")
_TABLE_ACL = re.compile(
    r"^(grant|revoke)\s+(.+?)\s+on\s+(?:table\s+)?(.+?)\s+(to|from)\s+(.+)$"
)
_FUNCTION_ACL = re.compile(
    r"^(grant|revoke)\s+(.+?)\s+on\s+function\s+"
    r"public\.has_store_access\s*\(\s*uuid\s*\)\s+(to|from)\s+(.+)$"
)
_DROP_POLICY = re.compile(
    r"^drop\s+policy\s+if\s+exists\s+([a-z_][a-z0-9_]*)\s+on\s+"
    r"(public\.[a-z_][a-z0-9_]*)$"
)
_CREATE_POLICY = re.compile(
    r"^create\s+policy\s+([a-z_][a-z0-9_]*)\s+on\s+"
    r"(public\.[a-z_][a-z0-9_]*)\s+(.+)$"
)
_POLICY_ROLES = re.compile(r"\bto\s+(.+?)\s+(?:using|with\s+check)\s*\(")
_AUTH_UID_NOT_NULL = re.compile(
    r"\(\s*select\s+auth\.uid\s*\(\s*\)\s*\)\s+is\s+not\s+null"
)
_TASK_STATUS_GUARD = re.compile(r"\band\s+status\s*=\s*'pending'")
_TASK_STAGE_GUARD = re.compile(r"\band\s+current_stage\s*=\s*'ingestion'")
_AUDIT_SCOPE = re.compile(
    r"\(\s*store_id\s+is\s+not\s+null\s+and\s+"
    r"public\.has_store_access\s*\(\s*store_id\s*\)\s*\)\s+or\s+"
    r"\(\s*store_id\s+is\s+null\s+and\s+user_id\s*=\s*"
    r"\(\s*select\s+auth\.uid\s*\(\s*\)\s*\)\s*\)"
)


def _normalised_statements(text: str) -> list[str]:
    """Split SQL outside comments, quotes, and dollar-quoted function bodies."""

    statements: list[str] = []
    current: list[str] = []
    state = "normal"
    dollar_tag = ""
    index = 0

    while index < len(text):
        if state == "line_comment":
            if text[index] in "\r\n":
                current.append(" ")
                state = "normal"
            index += 1
            continue

        if state == "block_comment":
            if text.startswith("*/", index):
                current.append(" ")
                state = "normal"
                index += 2
            else:
                index += 1
            continue

        if state == "single_quote":
            current.append(text[index])
            if text[index] == "'":
                if index + 1 < len(text) and text[index + 1] == "'":
                    current.append(text[index + 1])
                    index += 2
                    continue
                state = "normal"
            index += 1
            continue

        if state == "double_quote":
            current.append(text[index])
            if text[index] == '"':
                if index + 1 < len(text) and text[index + 1] == '"':
                    current.append(text[index + 1])
                    index += 2
                    continue
                state = "normal"
            index += 1
            continue

        if state == "dollar_quote":
            if text.startswith(dollar_tag, index):
                current.append(dollar_tag)
                index += len(dollar_tag)
                state = "normal"
            else:
                current.append(text[index])
                index += 1
            continue

        if text.startswith("--", index):
            state = "line_comment"
            index += 2
            continue
        if text.startswith("/*", index):
            state = "block_comment"
            index += 2
            continue
        if text[index] == "'":
            state = "single_quote"
            current.append(text[index])
            index += 1
            continue
        if text[index] == '"':
            state = "double_quote"
            current.append(text[index])
            index += 1
            continue
        if text[index] == "$":
            match = _DOLLAR_QUOTE.match(text, index)
            if match:
                dollar_tag = match.group(0)
                state = "dollar_quote"
                current.append(dollar_tag)
                index = match.end()
                continue
        if text[index] == ";":
            statement = " ".join("".join(current).lower().split())
            if statement:
                statements.append(statement)
            current = []
            index += 1
            continue

        current.append(text[index])
        index += 1

    statement = " ".join("".join(current).lower().split())
    if statement:
        statements.append(statement)
    return statements


def _items(value: str) -> set[str]:
    return {
        item.strip().replace("all privileges", "all")
        for item in value.split(",")
        if item.strip()
    }


def _comma_items(value: str) -> list[str]:
    """Split a SQL comma list without splitting a column privilege list."""

    items: list[str] = []
    current: list[str] = []
    depth = 0
    for character in value:
        if character == "(":
            depth += 1
        elif character == ")" and depth:
            depth -= 1
        if character == "," and depth == 0:
            item = "".join(current).strip()
            if item:
                items.append(item)
            current = []
        else:
            current.append(character)
    item = "".join(current).strip()
    if item:
        items.append(item)
    return items


def _acl_privileges(value: str) -> tuple[set[str], dict[str, set[str]]]:
    table_privileges: set[str] = set()
    column_privileges: dict[str, set[str]] = {}
    for item in _comma_items(value):
        item = item.replace("all privileges", "all")
        match = re.fullmatch(r"([a-z_]+)(?:\s*\((.*)\))?", item)
        if not match:
            table_privileges.add(f"unparsed:{item}")
            continue
        privilege, columns = match.groups()
        if columns is None:
            table_privileges.add(privilege)
        else:
            column_privileges.setdefault(privilege, set()).update(_items(columns))
    return table_privileges, column_privileges


def _check_table_privileges(statements: list[str]) -> list[str]:
    problems: list[str] = []
    tables = set(MINIMUM_TABLE_PRIVILEGES)
    public_revoke: set[str] = set()
    anon_revoke: set[str] = set()
    authenticated_revoke: set[str] = set()
    authenticated_grants: dict[str, set[str]] = {
        table: set() for table in tables
    }
    authenticated_column_grants: dict[str, dict[str, set[str]]] = {
        table: {} for table in tables
    }

    for statement in statements:
        match = _TABLE_ACL.fullmatch(statement)
        if not match:
            continue
        action, privilege_text, table_text, direction, role_text = match.groups()
        privileges, column_privileges = _acl_privileges(privilege_text)
        statement_tables = _items(table_text) & tables
        roles = _items(role_text)
        if not statement_tables:
            continue

        if action == "revoke" and direction == "from" and "all" in privileges:
            if "public" in roles:
                public_revoke.update(statement_tables)
            if "anon" in roles:
                anon_revoke.update(statement_tables)
            if "authenticated" in roles:
                authenticated_revoke.update(statement_tables)
        if action != "grant" or direction != "to":
            continue

        if roles & {"anon", "public"}:
            for table in sorted(statement_tables):
                problems.append(f"hardening migration grants a public role on {table}")
        if "authenticated" in roles:
            for table in statement_tables:
                authenticated_grants[table].update(privileges)
                for privilege, columns in column_privileges.items():
                    authenticated_column_grants[table].setdefault(
                        privilege, set()
                    ).update(columns)

    for table, expected in MINIMUM_TABLE_PRIVILEGES.items():
        if table not in public_revoke:
            problems.append(
                f"hardening migration must revoke all table privileges from public: {table}"
            )
        if table not in anon_revoke:
            problems.append(
                f"hardening migration must revoke all table privileges from anon: {table}"
            )
        if table not in authenticated_revoke:
            problems.append(
                f"hardening migration must reset authenticated table privileges: {table}"
            )
        actual = authenticated_grants[table]
        if actual != expected:
            problems.append(
                "hardening migration authenticated privileges mismatch for "
                f"{table}: expected {', '.join(sorted(expected))}; "
                f"got {', '.join(sorted(actual)) or 'none'}"
            )
        expected_columns = (
            {"insert": set(TASK_INSERT_COLUMNS)}
            if table == "public.tasks"
            else {}
        )
        actual_columns = authenticated_column_grants[table]
        if actual_columns != expected_columns:
            actual_insert = actual_columns.get("insert", set())
            problems.append(
                "hardening migration tasks insert columns mismatch: expected "
                f"{', '.join(sorted(TASK_INSERT_COLUMNS))}; "
                f"got {', '.join(sorted(actual_insert)) or 'none'}"
                if table == "public.tasks"
                else f"hardening migration must not grant column privileges on {table}"
            )
    return problems


def _check_hardening_basics(statements: list[str]) -> list[str]:
    problems: list[str] = []
    for table in MINIMUM_TABLE_PRIVILEGES:
        rls_statement = f"alter table {table} enable row level security"
        if statements.count(rls_statement) != 1:
            problems.append(
                f"hardening migration must enable RLS exactly once: {table}"
            )

    schema_grants: set[str] = set()
    for statement in statements:
        match = re.fullmatch(
            r"grant\s+(.+?)\s+on\s+schema\s+public\s+to\s+(.+)",
            statement,
        )
        if not match:
            continue
        privileges, roles = match.groups()
        parsed_roles = _items(roles)
        if parsed_roles & {"public", "anon"}:
            problems.append("hardening migration must not grant public schema access")
        if "authenticated" in parsed_roles:
            schema_grants.update(_items(privileges))
    if schema_grants != {"usage"}:
        problems.append(
            "hardening migration must grant only schema usage to authenticated"
        )
    return problems


def _check_function_privileges(statements: list[str]) -> list[str]:
    problems: list[str] = []
    revoked_roles: set[str] = set()
    granted_roles: set[str] = set()
    granted_privileges: set[str] = set()

    for statement in statements:
        match = _FUNCTION_ACL.fullmatch(statement)
        if not match:
            continue
        action, privilege_text, direction, role_text = match.groups()
        privileges = _items(privilege_text)
        roles = _items(role_text)
        if (
            action == "revoke"
            and direction == "from"
            and privileges & {"execute", "all"}
        ):
            revoked_roles.update(roles)
        if action == "grant" and direction == "to":
            granted_roles.update(roles)
            granted_privileges.update(privileges)

    for role in ("public", "anon", "authenticated"):
        if role not in revoked_roles:
            problems.append(f"has_store_access must revoke execute from {role}")
    if granted_roles != {"authenticated"} or granted_privileges != {"execute"}:
        problems.append("has_store_access execute must be granted only to authenticated")

    definitions = [
        statement
        for statement in statements
        if statement.startswith(
            "create or replace function public.has_store_access("
        )
    ]
    if len(definitions) != 1:
        problems.append("hardening migration must replace has_store_access exactly once")
    else:
        definition = definitions[0]
        if "security definer" not in definition or "set search_path = ''" not in definition:
            problems.append(
                "has_store_access must remain security definer with an empty search_path"
            )
        if not _AUTH_UID_NOT_NULL.search(definition):
            problems.append("has_store_access must require a non-null auth.uid()")
    return problems


def _check_policies(statements: list[str]) -> list[str]:
    problems: list[str] = []
    drops: list[tuple[str, str]] = []
    creates: dict[str, list[tuple[str, str, set[str]]]] = {}

    for statement in statements:
        drop_match = _DROP_POLICY.fullmatch(statement)
        if drop_match:
            drops.append(drop_match.groups())
            continue

        create_match = _CREATE_POLICY.fullmatch(statement)
        if not create_match:
            continue
        name, table, remainder = create_match.groups()
        role_match = _POLICY_ROLES.search(remainder)
        roles = _items(role_match.group(1)) if role_match else set()
        creates.setdefault(name, []).append((table, statement, roles))
        if roles != {"authenticated"}:
            problems.append(f"hardening policy must target authenticated only: {name}")

    for name, table in POLICY_TABLES.items():
        if drops.count((name, table)) != 1:
            problems.append(
                f"hardening migration must drop policy exactly once: {name} on {table}"
            )
        policy_creates = creates.get(name, [])
        if len(policy_creates) != 1:
            problems.append(
                f"hardening migration must recreate policy exactly once: {name} on {table}"
            )
            continue
        actual_table, statement, roles = policy_creates[0]
        if actual_table != table:
            problems.append(
                f"hardening migration recreates {name} on {actual_table}, expected {table}"
            )
        if not _AUTH_UID_NOT_NULL.search(statement):
            problems.append(
                f"hardening policy must require a non-null auth.uid(): {name}"
            )
        if name == "tasks_member_insert":
            if not _TASK_STATUS_GUARD.search(statement):
                problems.append(
                    "tasks_member_insert must require status = 'pending'"
                )
            if not _TASK_STAGE_GUARD.search(statement):
                problems.append(
                    "tasks_member_insert must require current_stage = 'ingestion'"
                )
        if name == "audit_member_read" and not _AUDIT_SCOPE.search(statement):
            problems.append(
                "audit_member_read must limit null-store events to user_id = auth.uid()"
            )

    return problems


def _check_hardening_migration(text: str) -> list[str]:
    statements = _normalised_statements(text)
    return (
        _check_hardening_basics(statements)
        + _check_table_privileges(statements)
        + _check_function_privileges(statements)
        + _check_policies(statements)
    )


def check() -> list[str]:
    if not MIGRATION.is_file():
        return ["missing 001_initial_schema.sql"]
    text = MIGRATION.read_text(encoding="utf-8").lower()
    problems = [
        f"migration missing required contract: {snippet}"
        for snippet in REQUIRED_SNIPPETS
        if snippet.lower() not in text
    ]
    problems.extend(
        f"migration contains forbidden public contract: {snippet}"
        for snippet in FORBIDDEN_SNIPPETS
        if snippet.lower() in text
    )
    if not INDEX_MIGRATION.is_file():
        problems.append("missing 002_indexes.sql")
    else:
        index_text = INDEX_MIGRATION.read_text(encoding="utf-8").lower()
        problems.extend(
            f"index migration missing required contract: {snippet}"
            for snippet in REQUIRED_INDEX_SNIPPETS
            if snippet.lower() not in index_text
        )
    if not HARDENING_MIGRATION.is_file():
        problems.append("missing 003_authenticated_only.sql")
    else:
        problems.extend(
            _check_hardening_migration(
                HARDENING_MIGRATION.read_text(encoding="utf-8")
            )
        )
    return problems


if __name__ == "__main__":
    problems = check()
    if problems:
        raise SystemExit("\n".join(problems))
    print("migration_contract=passed")
