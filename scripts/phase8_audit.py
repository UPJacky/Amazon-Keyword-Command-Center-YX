#!/usr/bin/env python3
"""Phase 8 local deployment/security audit; never contacts external services."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from supabase.migration_contract_check import check as check_migration_contract
from scripts.build_pages_demo import audit_demo_output, build, expected_demo_files



def audit() -> dict[str, object]:
    required = [
        "AGENTS.md", "README.md", "scripts/run_uat.py", "scripts/run_worker_loop.py",
        "scripts/run_worker_loop.ps1",
        "scripts/check_worker_loops.py",
        "supabase/migrations/001_initial_schema.sql", "supabase/migration_contract_check.py",
        "supabase/migrations/002_indexes.sql", "supabase/migrations/003_authenticated_only.sql",
        "scripts/check_continuous_execution.py",
        "scripts/check_phase8_documentation.py", "scripts/check_frontend_syntax.py",
        "docs/acceptance/phase8-local-audit.md", "docs/acceptance/phase8-delivery-audit.md", "docs/acceptance/continuous-supervision.md",
        "docs/acceptance/uat-local.md", "docs/deployment/pages-demo.md",
        "frontend/login.html", "frontend/report.html", "frontend/tool/index.html", "frontend/tool/tool.js", "frontend/report/index.html", "frontend/app.js", "frontend/contract_check.py",
        "scripts/build_pages_demo.py", "scripts/test_build_pages_demo.py", "rules/definitions/action_mapping.json",
    ]
    missing = [path for path in required if not (ROOT / path).is_file()]
    migration = (ROOT / "supabase" / "migrations" / "001_initial_schema.sql").read_text(encoding="utf-8").lower()
    pages_builder = (ROOT / "scripts" / "build_pages_demo.py").read_text(encoding="utf-8")
    phase8_doc = (ROOT / "docs" / "acceptance" / "phase8-local-audit.md").read_text(encoding="utf-8")
    supervision_doc = (ROOT / "docs" / "acceptance" / "continuous-supervision.md").read_text(encoding="utf-8")
    with tempfile.TemporaryDirectory(prefix="kwcc-phase8-pages-") as temporary:
        pages_output = build(Path(temporary) / "site")
        pages_errors = audit_demo_output(pages_output)
        pages_files = {
            path.relative_to(pages_output).as_posix()
            for path in pages_output.rglob("*")
            if path.is_file()
        }
    expected_pages_files = expected_demo_files()
    module_routes = {f"report/{name}.html" for name in ("index", "rank", "negative", "competitors", "listing", "optimization")}
    rls_markers = ["alter table public.tasks enable row level security", "alter table public.task_runs enable row level security", "create policy runs_member_read", "report_path text"]
    frontend = "\n".join((ROOT / name).read_text(encoding="utf-8") for name in ("frontend/app.js", "frontend/report.html", "frontend/report/index.html"))
    local_checks = {
        "required_files": not missing,
        "migration_rls_private_report_contract": not check_migration_contract() and all(marker in migration for marker in rls_markers),
        "migration_indexes_present": (ROOT / "supabase" / "migrations" / "002_indexes.sql").is_file(),
        "frontend_session_guard": "kwcc_demo_session" in frontend and "login.html" in frontend,
        "pages_demo_output_audit": not pages_errors and pages_files == expected_pages_files and module_routes <= pages_files,
        "pages_builder_is_local_only": all(marker not in pages_builder.lower() for marker in ("requests", "urllib", "httpx", "socket", "subprocess")) and '"published": False' in pages_builder,
        "phase8_docs_declare_local_only": "UAT 网络调用为 0" in phase8_doc and "不能伪装为通过" in phase8_doc,
        "supervision_docs_declare_no_early_stop": "完整 UAT 通过" in supervision_doc and "不能直接收尾" in supervision_doc,
        "no_public_report_bucket_config": not any((ROOT / name).is_file() for name in ("nginx.conf", "docker-compose.yml", "docker-compose.yaml")),
        "worker_loop_entry": (ROOT / "scripts" / "run_worker_loop.py").is_file() and (ROOT / "scripts" / "run_worker_loop.ps1").is_file(),
    }
    external_confirmation_required = [
        "execute Supabase migrations in a disposable project and verify RLS with two users",
        "publish frontend on GitHub Pages and verify exact HTTPS/CORS/Auth redirect origin",
        "verify private Storage report reads with real authenticated user",
        "verify actual Provider tools/list schema, cost, units and rate limiting",
    ]
    return {
        "passed": not missing and all(local_checks.values()),
        "local_checks": local_checks,
        "missing": missing,
        "network_calls": 0,
        "external_calls": 0,
        "local_only": True,
        "external_confirmation_required": external_confirmation_required,
    }


if __name__ == "__main__":
    result = audit()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result["passed"] else 1)
