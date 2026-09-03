"""Static checks for the local frontend contract."""

from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parent
MODULE_PAGES = tuple(f"report/{name}.html" for name in ("rank", "negative", "competitors", "listing", "optimization"))
PAGES = ("index.html", "login.html", "workspace.html", "tasks.html", "strategy.html", "report.html", "tool/index.html", "report/index.html") + MODULE_PAGES
PROTECTED_PAGES = ("workspace.html", "tasks.html", "strategy.html", "report.html", "tool/index.html", "report/index.html") + MODULE_PAGES
SECRET_PATTERN = re.compile(r"service_role|sb_secret_|AKIA[0-9A-Z]{16}|豆包 API Key|MCP Token", re.I)
SESSION_GUARD_MARKERS = ("kwcc_demo_session", "window.location.replace(loginUrl)")
LOGOUT_MARKER = "a[href=\"login.html\"]"


def has_secret_like_text(text: str, filename: str) -> bool:
    # Only this exact rejection expression is a reviewed code literal, not config.
    # Do not exempt client.js as a whole or suppress actual key assignments.
    guard = "    if (/service_role|sb_secret_/i.test(value) || jwtPayload(value)?.role === 'service_role')"
    if filename == "client.js":
        text = "\n".join(line for line in text.splitlines() if line != guard)
    return SECRET_PATTERN.search(text) is not None


def check() -> list[str]:
    errors: list[str] = []
    for page in PAGES:
        path = ROOT / page
        if not path.is_file():
            errors.append(f"missing page: {page}")
            continue
        text = path.read_text(encoding="utf-8")
        for asset in ("styles.css", "public-config.js", "client.js", "app.js"):
            if asset not in text:
                errors.append(f"{page} missing local asset reference: {asset}")
        if SECRET_PATTERN.search(text):
            errors.append(f"secret-like text in {page}")
    for path in ROOT.rglob("*.js"):
        if "tests" in path.parts:
            continue
        if has_secret_like_text(path.read_text(encoding="utf-8"), path.name):
            errors.append(f"secret-like text in {path.name}")
    report_text = (ROOT / "report.html").read_text(encoding="utf-8") + (ROOT / "report" / "index.html").read_text(encoding="utf-8")
    report_script = (ROOT / "report.js").read_text(encoding="utf-8") if (ROOT / "report.js").is_file() else ""
    for marker in ("report.js", "report-rows", "data-action-filter", "report-schema-version", "report-currency", "report-reconciliation", "report-input-file", "report-input-sha256", "report-provider-version", "report-missing-fields", "report-period-currency", "data-action-filter=\"keep\"", "data-action-filter=\"cautious\"", "data-action-filter=\"stop_loss\""):
        if marker not in report_text:
            errors.append(f"report.html missing dynamic report marker: {marker}")
    for marker in ("master-table.json", "market-demo-modules", "fetch(", "URL.createObjectURL", "report-rows", "Module 02", "Module 03", "schema_version", "input_file", "currency_code", "input_sha256", "provider_snapshot_version", "report-input-file", "report-period-currency", "stop_loss", "reduce_or_pause", "toLocaleString"):
        if marker not in report_script:
            errors.append(f"report.js missing artifact/UI marker: {marker}")
    for page, script, markers in (
        ("tasks.html", "tasks.js", ("task-rows", "task-count")),
        ("strategy.html", "strategy.js", ("strategy-config-version", "strategy-local-values")),
    ):
        page_text = (ROOT / page).read_text(encoding="utf-8")
        script_text = (ROOT / script).read_text(encoding="utf-8") if (ROOT / script).is_file() else ""
        if script not in page_text:
            errors.append(f"{page} missing local data script: {script}")
        for marker in markers:
            if marker not in page_text and marker not in script_text:
                errors.append(f"{page}/{script} missing local data marker: {marker}")
    task_script = (ROOT / "tasks.js").read_text(encoding="utf-8")
    for marker in ("schema_version", "input_file", "input_sha256", "currency_code", "rule_version", "config_version", "provider_snapshot_version", "reconciliation_passed", "missing_fields"):
        if marker not in task_script:
            errors.append(f"tasks.js missing report traceability field: {marker}")
    artifact = ROOT.parent / "data" / "golden" / "market-demo-report" / "master-table.json"
    action_artifact = ROOT.parent / "data" / "golden" / "market-demo-report" / "action-results.json"
    meta_artifact = ROOT.parent / "data" / "golden" / "market-demo-report" / "report-meta.json"
    if not artifact.is_file():
        errors.append("missing report-0.2 artifact: market-demo-report/master-table.json")
    else:
        import json
        report = json.loads(artifact.read_text(encoding="utf-8"))
        for marker in ("schema_version", "currency_code", "input_sha256", "provider_snapshot_version", "reconciliation", "rows", "missing_fields"):
            if marker not in report:
                errors.append(f"report artifact missing top-level field: {marker}")
        if report.get("schema_version") != "report-0.2":
            errors.append("report artifact schema is not report-0.2")
        if not report.get("currency_code") or not re.fullmatch(r"[A-Z]{3}", report["currency_code"]):
            errors.append("report artifact currency_code is not ISO-4217-like")
        if not isinstance(report.get("rows"), list) or not report["rows"]:
            errors.append("report artifact rows are empty or invalid")
        else:
            for index, row in enumerate(report["rows"]):
                if "action_group" not in row or "ui_conclusion" not in row or "missing_fields" not in row:
                    errors.append(f"report artifact row {index} missing action/missingness fields")
        if not isinstance(report.get("missing_fields"), list):
            errors.append("report artifact missing_fields must be a list")
        if not action_artifact.is_file():
            errors.append("missing action artifact: market-demo-report/action-results.json")
        else:
            actions = json.loads(action_artifact.read_text(encoding="utf-8"))
            for marker in ("schema_version", "input_file", "input_sha256", "currency_code", "rule_version", "config_version", "provider_snapshot_version", "reconciliation_passed", "missing_fields", "rows"):
                if marker not in actions:
                    errors.append(f"action artifact missing traceability field: {marker}")
            for marker in ("schema_version", "input_file", "input_sha256", "currency_code", "rule_version", "config_version", "provider_snapshot_version", "missing_fields"):
                if actions.get(marker) != report.get(marker):
                    errors.append(f"action artifact field does not match master report: {marker}")
            if actions.get("reconciliation_passed") != (report.get("reconciliation", {}).get("passed") is True):
                errors.append("action reconciliation_passed does not match master report")
            if actions.get("rows") != report.get("rows"):
                errors.append("action rows do not match master report rows")
            if actions.get("missing_fields") != report.get("missing_fields"):
                errors.append("action missing_fields does not match master report")
        if not meta_artifact.is_file():
            errors.append("missing report-meta artifact: market-demo-report/report-meta.json")
        else:
            meta = json.loads(meta_artifact.read_text(encoding="utf-8"))
            for marker in ("schema_version", "input_file", "input_sha256", "currency_code", "rule_version", "config_version", "provider_snapshot_version", "reconciliation_passed", "missing_fields"):
                if marker not in meta:
                    errors.append(f"report meta artifact missing traceability field: {marker}")
            if not isinstance(meta.get("missing_fields"), list):
                errors.append("report meta missing_fields must be a list")
            if isinstance(report, dict):
                for marker in ("schema_version", "input_file", "input_sha256", "currency_code", "rule_version", "config_version", "provider_snapshot_version", "missing_fields"):
                    if meta.get(marker) != report.get(marker):
                        errors.append(f"report meta field does not match master report: {marker}")
                if meta.get("reconciliation_passed") != (report.get("reconciliation", {}).get("passed") is True):
                    errors.append("report meta reconciliation_passed does not match master report")
    task_runner = (ROOT.parent / "worker" / "pipeline" / "task_runner.py").read_text(encoding="utf-8")
    for marker in ("shared_traceability", '"run-meta.json"', '"task_id"', '"run_id"', '"current_stage"'):
        if marker not in task_runner:
            errors.append(f"task runner missing run-meta traceability marker: {marker}")
    app_text = (ROOT / "app.js").read_text(encoding="utf-8")
    for marker in SESSION_GUARD_MARKERS:
        if marker not in app_text:
            errors.append(f"app.js missing session guard marker: {marker}")
    if LOGOUT_MARKER not in app_text or "localStorage.removeItem('kwcc_demo_session')" not in app_text:
        errors.append("app.js missing demo logout session cleanup")
    for page in PROTECTED_PAGES:
        body = (ROOT / page).read_text(encoding="utf-8").split("<body", 1)[1].split(">", 1)[0]
        if "data-page=" not in body and "app-shell" not in body:
            errors.append(f"{page} missing protected body marker")
    return errors


if __name__ == "__main__":
    problems = check()
    if problems:
        raise SystemExit("\n".join(problems))
    print("frontend_contract=passed")
