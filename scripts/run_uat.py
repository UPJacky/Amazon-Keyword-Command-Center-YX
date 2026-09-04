#!/usr/bin/env python3
"""Run local UAT gates without network or external credentials."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import importlib.util
import tempfile
import re
from contextlib import ExitStack
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_GATE_COUNT = 20
DEFAULT_GATE_TIMEOUT_SECONDS = 120
SUMMARY_REQUIRED_FIELDS = ("network_calls", "external_calls", "local_only")
# Match executable gates only; the Pages unit-test gate has no JSON process summary.
STRUCTURED_SUMMARY_GATES = ("scripts/check_worker_loops.py", "scripts/phase8_audit.py", "scripts/build_pages_demo.py")


def run(command: list[str], timeout: int = DEFAULT_GATE_TIMEOUT_SECONDS) -> dict[str, object]:
    try:
        process = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        return {
            "command": command,
            "passed": False,
            "timed_out": True,
            "test_counts": [],
            "stdout_tail": (exc.stdout or "")[-800:],
            "stderr_tail": (exc.stderr or "")[-800:],
        }
    except OSError as exc:
        return {
            "command": command,
            "passed": False,
            "timed_out": False,
            "test_counts": [],
            "stdout_tail": "",
            "stderr_tail": f"unable to start gate: {exc}",
        }
    combined = f"{process.stdout}\n{process.stderr}"
    counts = [int(value) for value in re.findall(r"Ran (\d+) tests? in ", combined)]
    summary = None
    try:
        summary = json.loads(process.stdout)
    except (TypeError, json.JSONDecodeError):
        pass
    return {
        "command": command,
        "passed": process.returncode == 0,
        "timed_out": False,
        "test_counts": counts,
        "summary": summary,
        "stdout_tail": process.stdout[-800:],
        "stderr_tail": process.stderr[-800:],
    }


def run_gate(command: list[str], timeout: int = DEFAULT_GATE_TIMEOUT_SECONDS) -> dict[str, object]:
    """Normalize an unexpected gate exception so later gates still run."""
    try:
        return run(command, timeout=timeout)
    except Exception as exc:  # keep UAT collection alive; do not catch interrupts
        return {
            "command": command,
            "passed": False,
            "timed_out": False,
            "test_counts": [],
            "stdout_tail": "",
            "stderr_tail": f"gate raised unexpected exception: {exc}",
            "exception_type": type(exc).__name__,
        }


def _summary_metrics(checks: list[dict[str, object]]) -> tuple[int, int, bool, list[str]]:
    """Aggregate child summaries without allowing malformed output to abort UAT."""
    network_calls = 0
    external_calls = 0
    local_only = True
    errors: list[str] = []
    for item in checks:
        command_text = " ".join(str(part) for part in item.get("command", []))
        summary = item.get("summary")
        if not isinstance(summary, dict):
            continue
        for field in ("network_calls", "external_calls"):
            value = summary.get(field, 0)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                errors.append(f"{command_text}: invalid {field}")
                continue
            if field == "network_calls":
                network_calls += value
            else:
                external_calls += value
        value = summary.get("local_only", True)
        if not isinstance(value, bool):
            errors.append(f"{command_text}: invalid local_only")
        elif not value:
            local_only = False
    return network_calls, external_calls, local_only, errors


def _structured_summary_errors(checks: list[dict[str, object]]) -> list[str]:
    """Require the complete boundary summary contract for executable gates."""
    errors: list[str] = []
    required = set(SUMMARY_REQUIRED_FIELDS)
    for item in checks:
        command_text = " ".join(str(part) for part in item.get("command", []))
        if not any(marker in command_text for marker in STRUCTURED_SUMMARY_GATES):
            continue
        summary = item.get("summary")
        if not isinstance(summary, dict):
            errors.append(f"{command_text}: missing structured summary")
            continue
        missing = sorted(required - set(summary))
        if missing:
            errors.append(f"{command_text}: missing summary fields: {', '.join(missing)}")
            continue
        for field in ("network_calls", "external_calls"):
            value = summary[field]
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                errors.append(f"{command_text}: invalid {field}")
        if not isinstance(summary["local_only"], bool):
            errors.append(f"{command_text}: invalid local_only")
    return errors


def select_python() -> str:
    """Use the current interpreter unless XLSX support needs the workspace bundle."""
    configured = os.environ.get("KWCC_PYTHON")
    if configured and Path(configured).is_file():
        return configured
    if importlib.util.find_spec("openpyxl") is not None:
        return sys.executable
    bundled = Path(r"C:\Users\Jacky\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe")
    if bundled.is_file():
        return str(bundled)
    return sys.executable


def main() -> int:
    python = select_python()
    with ExitStack() as temporary_stack:
        temporary_roots = [temporary_stack.enter_context(tempfile.TemporaryDirectory(prefix=prefix)) for prefix in (
            "kwcc-phase4-",
            "kwcc-competitors-",
            "kwcc-diagnostics-",
            "kwcc-optimization-",
            "kwcc-pages-",
        )]
        phase4_output = Path(temporary_roots[0])
        competitor_output = Path(temporary_roots[1]) / "competitors.json"
        diagnostics_output = Path(temporary_roots[2]) / "listing-diagnostics.json"
        optimization_output = Path(temporary_roots[3]) / "optimization-plan.json"
        pages_output = Path(temporary_roots[4]) / "site"
        checks = [
            run_gate([python, "-m", "unittest", "discover", "-s", "worker/tests", "-v"]),
            run_gate([python, "-m", "unittest", "discover", "-s", "frontend", "-p", "test_*.py", "-v"]),
            run_gate([python, "frontend/contract_check.py"]),
            run_gate([python, "scripts/check_frontend_syntax.py"]),
            run_gate([python, "scripts/check_continuous_execution.py"]),
            run_gate([python, "-m", "unittest", "scripts.test_continuous_execution", "scripts.test_project_supervisor", "-v"]),
            run_gate([python, "scripts/check_phase8_documentation.py"]),
            run_gate([python, "scripts/check_worker_loops.py"]),
            run_gate([python, "-m", "unittest", "scripts/test_uat_orchestration.py", "-v"]),
            run_gate([python, "rules/action_mapping_contract_check.py"]),
            run_gate([python, "supabase/migration_contract_check.py"]),
            run_gate([python, "-m", "unittest", "supabase.test_migration_contract", "supabase.test_production_jobs", "supabase.test_strategy_versions", "-v"]),
            run_gate([python, "scripts/smoke_test.py"]),
            run_gate([python, "scripts/build_phase4_modules.py", "--report", "data/golden/market-demo-report/master-table.json", "--output", str(phase4_output)]),
            run_gate([python, "scripts/build_competitor_profile.py", "--input", "data/golden/competitor-input-demo.json", "--output", str(competitor_output)]),
            run_gate([python, "scripts/build_listing_diagnostics.py", "--input", "data/golden/listing-diagnostics-input-demo.json", "--output", str(diagnostics_output)]),
            run_gate([python, "scripts/build_optimization_plan.py", "--report", "data/golden/market-demo-report/master-table.json", "--output", str(optimization_output)]),
            run_gate([python, "scripts/phase8_audit.py"]),
            run_gate([python, "scripts/build_pages_demo.py", "--output", str(pages_output)]),
            run_gate([python, "-m", "unittest", "scripts/test_build_pages_demo.py", "scripts/test_build_pages_live.py", "-v"]),
        ]
        migration = ROOT / "supabase" / "migrations"
        required_migrations = [
            migration / "001_initial_schema.sql",
            migration / "002_indexes.sql",
            migration / "003_authenticated_only.sql",
        ]
        migration_passed = all(path.is_file() for path in required_migrations)
        security_hits: list[str] = []
        secret_names = ("SUPABASE_SERVICE_KEY=", "XYDC_MCP_TOKEN=", "DOUBAO_API_KEY=")
        for path in ROOT.rglob("*"):
            if not path.is_file() or path.name in {".env.example", "run_uat.py"} or ".git" in path.parts:
                continue
            if path.suffix.lower() not in {".py", ".js", ".ts", ".tsx", ".html", ".sql", ".json", ".md"}:
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            for name in secret_names:
                if name in text and any(char not in " \t\r\n" for char in text.split(name, 1)[1].splitlines()[0]):
                    security_hits.append(str(path.relative_to(ROOT)))
        test_counts = {}
        for item in checks:
            counts = item.get("test_counts", [])
            if counts:
                command_text = " ".join(item["command"])
                if "worker/tests" in command_text:
                    test_counts["worker"] = counts[-1]
                elif "-s frontend" in command_text and "-p test_*.py" in command_text:
                    test_counts["frontend"] = counts[-1]
        required_counts_present = test_counts.get("worker", 0) > 0 and test_counts.get("frontend", 0) > 0
        gate_count_ok = len(checks) == EXPECTED_GATE_COUNT
        structured_summary_missing = [
            " ".join(item["command"])
            for item in checks
            if any(marker in " ".join(item["command"]) for marker in STRUCTURED_SUMMARY_GATES)
            and not isinstance(item.get("summary"), dict)
        ]
        network_calls, external_calls, local_only, summary_contract_errors = _summary_metrics(checks)
        summary_contract_errors.extend(_structured_summary_errors(checks))
        report = {
            "passed": all(item["passed"] for item in checks)
            and gate_count_ok
            and migration_passed
            and not security_hits
            and required_counts_present
            and not structured_summary_missing
            and not summary_contract_errors
            and network_calls == 0
            and external_calls == 0
            and local_only,
            "checks": checks,
            "gate_count": len(checks),
            "expected_gate_count": EXPECTED_GATE_COUNT,
            "gate_count_ok": gate_count_ok,
            "test_counts": test_counts,
            "required_counts_present": required_counts_present,
            "structured_summary_missing": structured_summary_missing,
            "summary_contract_errors": summary_contract_errors,
            "migration_files_present": migration_passed,
            "secret_value_hits": sorted(set(security_hits)),
            "network_calls": network_calls,
            "external_calls": external_calls,
            "local_only": local_only,
        }
        print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
