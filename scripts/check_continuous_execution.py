#!/usr/bin/env python3
"""Static contract check for the project's continuous execution workflow."""

from __future__ import annotations

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]

TERMINAL_EXECUTION_STATES = frozenset(
    {"BLOCKED_EXTERNAL", "BLOCKED_RISK", "USER_STOPPED", "PROJECT_COMPLETE"}
)
VALID_EXECUTION_STATES = frozenset({"RUNNING", *TERMINAL_EXECUTION_STATES})
STATUS_FIELDS = (
    "execution_state",
    "current_objective",
    "next_safe_action",
    "stop_reason",
    "last_action_fingerprint",
    "local_safe_queue",
    "external_blockers_only",
    "verified_gate_snapshot",
)
EMPTY_SCALARS = frozenset({"", "none", "null", "~", "n/a", "na", "[]", "{}", "-"})
VALID_LOCAL_QUEUE_STATES = frozenset({"empty", "in_progress"})

STATE_MACHINE_DOCUMENTS = (
    "AGENTS.md",
    "PROJECT_PLAN.md",
    "docs/acceptance/continuous-supervision.md",
)
STATE_MACHINE_MARKERS = (
    "RUNNING",
    "BLOCKED_EXTERNAL",
    "BLOCKED_RISK",
    "USER_STOPPED",
    "PROJECT_COMPLETE",
    "next_safe_action",
    "verified_gate_snapshot",
)
DEDUPLICATION_MARKERS = ("防重复", "去重", "不得重复", "跳过已验证", "dedup")
HEARTBEAT_MARKERS = ("心跳", "heartbeat")
RUNNING_ONLY_MARKERS = ("只在", "仅在", "只允许", "仅允许", "only")

REQUIRED_MARKERS = {
    "AGENTS.md": (
        "执行器防早停清单（强制）",
        "单次任务成功不得作为连续开发完成信号",
        "状态重读 → 本地任务清点 → Gate 汇总 → 阻塞确认",
        "主 Agent 与子 Agent 监督",
        "关闭并释放 Agent 槽位",
        "跨轮持续唤醒",
        "PROJECT_TASKS.json",
        "scripts/project_supervisor.py",
        "--claim",
        "--claim-external",
        "--authorization-json",
        "--block-external",
        "--reason-json",
        "--complete",
        "get_goal",
        "create_goal",
    ),
    "PROJECT_PLAN.md": (
        "14.3 连续执行与多 Agent 监督协议",
        "主 Agent 以项目目标为唯一总目标",
        "不得把这段开工模板当作当前会话的自动收尾指令",
        "心跳自动化只在",
        "关闭释放并发槽位",
        "PROJECT_TASKS.json",
        "scripts/project_supervisor.py",
        "--claim",
        "--claim-external",
        "--block-external",
        "--complete",
        "get_goal",
        "create_goal",
    ),
    "docs/acceptance/continuous-supervision.md": (
        "主 Agent 职责",
        "子 Agent 交付格式",
        "强制续行闭环",
        "只冻结对应外部 Gate",
        "释放 Agent 槽位",
        "心跳自动化",
        "get_goal",
        "create_goal",
    ),
    "docs/acceptance/project-supervisor.md": (
        "PROJECT_TASKS.json",
        "input_fingerprint",
        "verified_fingerprint",
        "stale",
        "next_task",
        "RUNNING",
        "--claim",
        "--claim-external",
        "--authorization-json",
        "--block-external",
        "--reason-json",
        "--complete",
    ),
    "docs/acceptance/uat-local.md": (
        "continuous-supervision.md",
        "不替代真实 Supabase、Storage、Provider 和部署验收",
        "check_frontend_syntax.py",
        "002_indexes.sql",
    ),
    "README.md": (
        "run_worker_once.py` 只处理一个任务后退出",
        "run_worker_loop.ps1",
        "scripts/project_supervisor.py",
        "--claim",
        "--claim-external",
        "--block-external",
        "--complete",
    ),
    "CODEX_CONTINUOUS_SETUP.md": (
        "PROJECT_TASKS.json",
        "scripts/project_supervisor.py",
        "BLOCKED_EXTERNAL",
        "PROJECT_COMPLETE",
        "--claim",
        "--claim-external",
        "--block-external",
        "--complete",
        "get_goal",
        "create_goal",
    ),
}


def _normalise_scalar(raw_value: str) -> str:
    value = raw_value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        value = value[1:-1].strip()
    return value


def _is_concrete(value: str) -> bool:
    return value.strip().casefold() not in EMPTY_SCALARS


def _parse_status_header(content: str) -> tuple[dict[str, str], list[str]]:
    """Parse top-level scalar fields from the first YAML front matter block only."""

    lines = content.lstrip("\ufeff").splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, ["PROJECT_STATUS.md: top YAML header missing"]

    closing_index = None
    for index, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            closing_index = index
            break
        if re.match(r"^#{1,6}\s+", line):
            return {}, ["PROJECT_STATUS.md: top YAML header is not closed before first heading"]
    if closing_index is None:
        return {}, ["PROJECT_STATUS.md: top YAML header is not closed"]

    values: dict[str, str] = {}
    errors: list[str] = []
    field_pattern = re.compile(r"^([A-Za-z_][A-Za-z0-9_-]*):(?:\s*(.*))?$")
    for line_number, line in enumerate(lines[1:closing_index], start=2):
        match = field_pattern.match(line)
        if match is None:
            continue
        key, raw_value = match.groups()
        if key not in STATUS_FIELDS:
            continue
        if key in values:
            errors.append(f"PROJECT_STATUS.md: duplicate top header field: {key} (line {line_number})")
            continue
        values[key] = _normalise_scalar(raw_value or "")

    for field in STATUS_FIELDS:
        if field not in values:
            errors.append(f"PROJECT_STATUS.md: top header field missing: {field}")
    return values, errors


def _has_snapshot_deduplication_rule(content: str) -> bool:
    folded = content.casefold()
    return "verified_gate_snapshot" in content and any(
        marker.casefold() in folded for marker in DEDUPLICATION_MARKERS
    )


def _has_running_heartbeat_rule(content: str) -> bool:
    for paragraph in re.split(r"\n\s*\n", content):
        folded = " ".join(paragraph.casefold().split())
        if (
            "running" in folded
            and any(marker.casefold() in folded for marker in HEARTBEAT_MARKERS)
            and any(marker.casefold() in folded for marker in RUNNING_ONLY_MARKERS)
        ):
            return True
    return False


def _check_state_machine_documents(root: Path, errors: list[str]) -> None:
    for relative in STATE_MACHINE_DOCUMENTS:
        path = root / relative
        if not path.is_file():
            errors.append(f"{relative}: file missing")
            continue
        content = path.read_text(encoding="utf-8")
        for marker in STATE_MACHINE_MARKERS:
            if marker not in content:
                errors.append(f"{relative}: state-machine marker missing: {marker}")
        if not _has_snapshot_deduplication_rule(content):
            errors.append(f"{relative}: verified gate snapshot deduplication rule missing")
        if not _has_running_heartbeat_rule(content):
            errors.append(f"{relative}: heartbeat RUNNING-only rule missing")


def _check_project_status(root: Path, errors: list[str]) -> None:
    relative = "PROJECT_STATUS.md"
    path = root / relative
    if not path.is_file():
        errors.append(f"{relative}: file missing")
        return

    fields, parse_errors = _parse_status_header(path.read_text(encoding="utf-8"))
    errors.extend(parse_errors)
    if parse_errors:
        return

    state = fields["execution_state"]
    if state not in VALID_EXECUTION_STATES:
        allowed = ", ".join(sorted(VALID_EXECUTION_STATES))
        errors.append(f"{relative}: invalid execution_state {state!r}; allowed: {allowed}")
        return

    if not _is_concrete(fields["current_objective"]):
        errors.append(f"{relative}: current_objective must be concrete")
    if not _is_concrete(fields["last_action_fingerprint"]):
        errors.append(f"{relative}: last_action_fingerprint must be concrete")
    if not _is_concrete(fields["verified_gate_snapshot"]):
        errors.append(f"{relative}: verified_gate_snapshot must be concrete")

    queue_state = fields["local_safe_queue"].casefold()
    if queue_state not in VALID_LOCAL_QUEUE_STATES:
        allowed = ", ".join(sorted(VALID_LOCAL_QUEUE_STATES))
        errors.append(f"{relative}: invalid local_safe_queue {fields['local_safe_queue']!r}; allowed: {allowed}")

    external_only = fields["external_blockers_only"].casefold()
    if external_only not in {"true", "false"}:
        errors.append(f"{relative}: external_blockers_only must be true or false")

    if state == "RUNNING" and not _is_concrete(fields["next_safe_action"]):
        errors.append(f"{relative}: RUNNING requires a concrete next_safe_action")
    if state == "RUNNING" and queue_state == "empty":
        errors.append(f"{relative}: RUNNING cannot have local_safe_queue=empty")
    if state in TERMINAL_EXECUTION_STATES and not _is_concrete(fields["stop_reason"]):
        errors.append(f"{relative}: {state} requires a concrete stop_reason")
    if state in {"BLOCKED_EXTERNAL", "BLOCKED_RISK", "PROJECT_COMPLETE"} and queue_state != "empty":
        errors.append(f"{relative}: {state} requires local_safe_queue=empty")
    if state == "BLOCKED_EXTERNAL" and external_only != "true":
        errors.append(f"{relative}: BLOCKED_EXTERNAL requires external_blockers_only=true")
    if state == "PROJECT_COMPLETE" and external_only != "false":
        errors.append(f"{relative}: PROJECT_COMPLETE requires external_blockers_only=false")


def check_contract(root: Path = ROOT) -> list[str]:
    missing: list[str] = []
    for relative, markers in REQUIRED_MARKERS.items():
        path = root / relative
        if not path.is_file():
            missing.append(f"{relative}: file missing")
            continue
        content = path.read_text(encoding="utf-8")
        for marker in markers:
            if marker not in content:
                missing.append(f"{relative}: marker missing: {marker}")
    _check_state_machine_documents(root, missing)
    _check_project_status(root, missing)
    return missing


def main() -> int:
    missing = check_contract()
    if missing:
        print("continuous_execution_contract: FAILED")
        print("\n".join(missing))
        return 1
    print("continuous_execution_contract: PASSED")
    print("local-only; network_calls=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
