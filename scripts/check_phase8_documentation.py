#!/usr/bin/env python3
"""Read-only consistency checks for Phase 8 and continuous supervision docs."""

from __future__ import annotations

from pathlib import Path
from datetime import date
import re


ROOT = Path(__file__).resolve().parents[1]

CURRENT_STATE_HEADING = "### 当前执行状态"
CURRENT_GATE_PATTERNS = {
    "worker": r"\bWorker\s+(\d+)\s*项",
    "frontend": r"前端\s+(\d+)\s*项",
    "orchestration": r"UAT\s*编排契约\s+(\d+)\s*项",
    "continuous": r"连续执行契约\s+(\d+)\s*项",
    "uat": r"完整\s*UAT\s+(\d+/\d+)\s*Gate",
    "pages": r"(?:Pages\s+|输出\s+)(\d+)(?:\s*个\s+allowlist)?\s*文件",
    "docs": r"文档契约\s+(\d+)\s*项",
    "network_calls": r"\bnetwork_calls\s*=\s*(\d+)\b",
    "external_calls": r"\bexternal_calls\s*=\s*(\d+)\b",
    "secrets": r"\bSecret(?:\s+value)?(?:\s+命中为)?\s*[=:：]?\s*(\d+)\b",
}


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def top_metadata_value(document: str, key: str) -> str | None:
    """Return a metadata value before the document's first Markdown heading."""
    for line in document.lstrip("\ufeff").splitlines():
        if re.match(r"^#{1,6}\s+", line):
            break
        match = re.fullmatch(rf"{re.escape(key)}\s*:\s*(.+)", line.strip())
        if match:
            return match.group(1).strip().strip('"\'')
    return None


def markdown_section(document: str, heading: str) -> str | None:
    """Return one exact section, bounded by the next same/higher-level heading."""
    lines = document.splitlines()
    starts = [index for index, line in enumerate(lines) if line.strip() == heading]
    if len(starts) != 1:
        return None

    start = starts[0]
    level = len(heading) - len(heading.lstrip("#"))
    end = len(lines)
    for index in range(start + 1, len(lines)):
        match = re.match(r"^(#{1,6})\s+", lines[index])
        if match and len(match.group(1)) <= level:
            end = index
            break
    return "\n".join(lines[start + 1 : end])


def verified_gate_snapshot(status: str) -> dict[str, str]:
    raw = top_metadata_value(status, "verified_gate_snapshot")
    if raw is None:
        return {}

    snapshot: dict[str, str] = {}
    for part in raw.split(";"):
        key, separator, value = part.strip().partition("=")
        if not separator or not key or not value or key in snapshot:
            return {}
        snapshot[key] = value
    return snapshot


def current_plan_gate_counts(plan: str) -> dict[str, str]:
    section = current_state_section(plan)
    if section is None:
        return {}

    counts: dict[str, str] = {}
    for key, pattern in CURRENT_GATE_PATTERNS.items():
        values = set(re.findall(pattern, section, flags=re.IGNORECASE))
        if len(values) != 1:
            return {}
        counts[key] = values.pop()
    return counts


def current_gate_counts_match(plan: str, status: str) -> bool:
    snapshot = verified_gate_snapshot(status)
    plan_counts = current_plan_gate_counts(plan)
    return bool(plan_counts) and all(snapshot.get(key) == value for key, value in plan_counts.items())


def current_state_section(plan: str) -> str | None:
    headings = re.findall(r"^### 当前执行状态(?:（\d{4}-\d{2}-\d{2}）)?\s*$", plan, flags=re.MULTILINE)
    return markdown_section(plan, headings[0].strip()) if len(headings) == 1 else None


def memory_counts_match(document: str, snapshot: dict[str, str]) -> bool:
    section = markdown_section(document, "## 当前验证快照")
    if section is None:
        return False
    return all(
        set(re.findall(CURRENT_GATE_PATTERNS[key], section)) == {snapshot.get(key)}
        for key in ("worker", "frontend")
    )


def has_valid_update_date(document: str) -> bool:
    value = top_metadata_value(document, "updated_at")
    try:
        return value is not None and date.fromisoformat(value).isoformat() == value
    except ValueError:
        return False


def main() -> int:
    status = read("PROJECT_STATUS.md")
    memory = read("MEMORY.md")
    project_memory = read("PROJECT_MEMORY.md")
    plan = read("PROJECT_PLAN.md")
    phase8 = read("docs/acceptance/phase8-local-audit.md")
    supervision = read("docs/acceptance/continuous-supervision.md")
    snapshot = verified_gate_snapshot(status)
    plan_current_state = current_state_section(plan)
    current_counts_match = current_gate_counts_match(plan, status)

    checks = {
        "status_phase": top_metadata_value(status, "current_phase") in {
            "Phase 8 / local-deployment-audit",
            "Phase 3–7 / six-module-workbench",
            "Phase 9 / six-module-data-completion",
            "Phase 10 / LUNU-04 six-module business completion",
        },
        "status_uat_counts": current_counts_match and all(key in snapshot for key in ("worker", "frontend")),
        "memory_uat_counts": memory_counts_match(memory, snapshot),
        "project_memory_uat_counts": memory_counts_match(project_memory, snapshot),
        "pages_count": current_counts_match and "pages" in snapshot,
        "plan_current_uat_is_latest": current_counts_match,
        "memory_date": has_valid_update_date(project_memory),
        "plan_date": has_valid_update_date(plan),
        "plan_current_state": plan_current_state is not None,
        "plan_next_definition": "### Phase 8 下一步定义" in plan,
        "external_gates": all(
            marker in phase8 and marker in supervision and marker in plan
            for marker in ("Supabase", "GitHub Pages", "Storage", "Provider")
        ),
        "continuous_loop": all(
            marker in supervision
            for marker in (
                "状态重读",
                "本地任务清点",
                "下一项安全工作",
                "20 个本地 Gate",
                "external_calls=0",
            )
        ),
        "uat_orchestration_count": (
            bool(snapshot.get("orchestration"))
            and f"UAT 编排契约 {snapshot['orchestration']} 项" in status
            and f"编排契约 {snapshot['orchestration']} 项" in project_memory
            and f"UAT 编排契约 {snapshot['orchestration']} 项" in plan
        ),
        "malformed_summary_boundary": all(
            "summary_contract_errors" in document
            for document in (status, project_memory, plan, phase8, supervision)
        ) and "摘要缺失" in phase8 and "必需字段" in phase8,
        "no_legacy_plan_stop": "完成后停止，等待确认" not in plan,
    }

    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        print("phase8_documentation_contract: FAILED")
        print("\n".join(failed))
        return 1
    print("phase8_documentation_contract: PASSED")
    print(f"checks={len(checks)}; network_calls=0; read_only=true")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
