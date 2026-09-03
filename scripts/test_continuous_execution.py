from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts import check_continuous_execution as contract


STATE_MACHINE_TEXT = """
execution_state uses RUNNING while work remains. The legal terminal states are
BLOCKED_EXTERNAL, BLOCKED_RISK, USER_STOPPED, and PROJECT_COMPLETE.
The next_safe_action drives progress. 防重复 compares verified_gate_snapshot and skips
an unchanged action. 心跳自动化只在 RUNNING 时保持运行，终止态必须暂停。
"""


class ContinuousExecutionContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self._write_required_documents()
        self._write_status("RUNNING", "run targeted tests", "none")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _write(self, relative: str, content: str) -> None:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def _write_required_documents(self) -> None:
        for relative, markers in contract.REQUIRED_MARKERS.items():
            content = "\n".join(markers)
            if relative in contract.STATE_MACHINE_DOCUMENTS:
                content += STATE_MACHINE_TEXT
            self._write(relative, content)

    def _write_status(
        self,
        state: str,
        next_action: str,
        stop_reason: str,
        *,
        current_objective: str = "keep the project moving",
        local_safe_queue: str | None = None,
        external_blockers_only: str | None = None,
        body: str = "",
    ) -> None:
        if local_safe_queue is None:
            local_safe_queue = "in_progress" if state == "RUNNING" else "empty"
        if external_blockers_only is None:
            external_blockers_only = "true" if state == "BLOCKED_EXTERNAL" else "false"
        self._write(
            "PROJECT_STATUS.md",
            "\n".join(
                (
                    "---",
                    f"execution_state: {state}",
                    f'current_objective: "{current_objective}"',
                    f'next_safe_action: "{next_action}"',
                    f'stop_reason: "{stop_reason}"',
                    'last_action_fingerprint: "test-fingerprint-v1"',
                    f"local_safe_queue: {local_safe_queue}",
                    f"external_blockers_only: {external_blockers_only}",
                    'verified_gate_snapshot: "worker=1; uat=1/1"',
                    "---",
                    body,
                )
            ),
        )

    def _status_errors(self) -> list[str]:
        return [
            error
            for error in contract.check_contract(self.root)
            if error.startswith("PROJECT_STATUS.md:")
        ]

    def test_running_with_concrete_next_action_passes(self) -> None:
        self.assertEqual([], contract.check_contract(self.root))

    def test_all_four_terminal_states_are_legal(self) -> None:
        for state in sorted(contract.TERMINAL_EXECUTION_STATES):
            with self.subTest(state=state):
                self._write_status(state, "none", f"reason for {state}")
                self.assertEqual([], self._status_errors())

    def test_unknown_execution_state_is_rejected(self) -> None:
        self._write_status("IDLE", "wait", "none")
        errors = self._status_errors()
        self.assertTrue(any("invalid execution_state 'IDLE'" in error for error in errors))

    def test_running_without_concrete_next_action_is_rejected(self) -> None:
        for next_action in ("", "none", "null", "N/A", "[]"):
            with self.subTest(next_action=next_action):
                self._write_status("RUNNING", next_action, "none")
                errors = self._status_errors()
                self.assertIn(
                    "PROJECT_STATUS.md: RUNNING requires a concrete next_safe_action",
                    errors,
                )

    def test_running_with_empty_local_queue_is_rejected(self) -> None:
        self._write_status(
            "RUNNING",
            "continue implementation",
            "none",
            local_safe_queue="empty",
        )
        self.assertIn(
            "PROJECT_STATUS.md: RUNNING cannot have local_safe_queue=empty",
            self._status_errors(),
        )

    def test_terminal_state_requires_concrete_stop_reason(self) -> None:
        self._write_status("BLOCKED_EXTERNAL", "none", "none")
        self.assertIn(
            "PROJECT_STATUS.md: BLOCKED_EXTERNAL requires a concrete stop_reason",
            self._status_errors(),
        )

    def test_required_status_field_must_be_in_top_header(self) -> None:
        self._write(
            "PROJECT_STATUS.md",
            "\n".join(
                (
                    "---",
                    "execution_state: RUNNING",
                    'current_objective: "move forward"',
                    'stop_reason: "none"',
                    'last_action_fingerprint: "test-fingerprint-v1"',
                    "local_safe_queue: in_progress",
                    "external_blockers_only: false",
                    'verified_gate_snapshot: "worker=1; uat=1/1"',
                    "---",
                    'next_safe_action: "body value must not count"',
                )
            ),
        )
        self.assertIn(
            "PROJECT_STATUS.md: top header field missing: next_safe_action",
            self._status_errors(),
        )

    def test_body_state_does_not_override_top_header(self) -> None:
        self._write_status(
            "RUNNING",
            "continue implementation",
            "none",
            body="execution_state: INVALID\nnext_safe_action: none",
        )
        self.assertEqual([], self._status_errors())

    def test_heading_cannot_implicitly_close_status_header(self) -> None:
        self._write(
            "PROJECT_STATUS.md",
            "\n".join(
                (
                    "---",
                    "execution_state: RUNNING",
                    'current_objective: "move forward"',
                    'next_safe_action: "continue implementation"',
                    'stop_reason: "none"',
                    'last_action_fingerprint: "test-fingerprint-v1"',
                    "local_safe_queue: in_progress",
                    "external_blockers_only: false",
                    'verified_gate_snapshot: "worker=1; uat=1/1"',
                    "## body starts without closing front matter",
                    "---",
                )
            ),
        )
        self.assertIn(
            "PROJECT_STATUS.md: top YAML header is not closed before first heading",
            self._status_errors(),
        )

    def test_blocked_external_requires_external_only_flag(self) -> None:
        self._write_status(
            "BLOCKED_EXTERNAL",
            "none",
            "credentials required",
            external_blockers_only="false",
        )
        self.assertIn(
            "PROJECT_STATUS.md: BLOCKED_EXTERNAL requires external_blockers_only=true",
            self._status_errors(),
        )

    def test_each_protocol_document_requires_state_machine_markers(self) -> None:
        target = contract.STATE_MACHINE_DOCUMENTS[-1]
        content = (self.root / target).read_text(encoding="utf-8")
        self._write(target, content.replace("PROJECT_COMPLETE", "PROJECT_DONE"))
        self.assertIn(
            f"{target}: state-machine marker missing: PROJECT_COMPLETE",
            contract.check_contract(self.root),
        )

    def test_snapshot_deduplication_rule_is_required(self) -> None:
        target = "AGENTS.md"
        content = (self.root / target).read_text(encoding="utf-8")
        for marker in contract.DEDUPLICATION_MARKERS:
            content = content.replace(marker, "")
        self._write(target, content)
        self.assertIn(
            f"{target}: verified gate snapshot deduplication rule missing",
            contract.check_contract(self.root),
        )

    def test_heartbeat_must_be_running_only(self) -> None:
        target = "PROJECT_PLAN.md"
        content = (self.root / target).read_text(encoding="utf-8")
        for marker in contract.RUNNING_ONLY_MARKERS:
            content = content.replace(marker, "")
        self._write(target, content)
        self.assertIn(
            f"{target}: heartbeat RUNNING-only rule missing",
            contract.check_contract(self.root),
        )

    def test_platform_goal_lifecycle_is_required(self) -> None:
        target = "AGENTS.md"
        content = (self.root / target).read_text(encoding="utf-8")
        self._write(target, content.replace("create_goal", "create_project_goal"))
        self.assertIn(
            f"{target}: marker missing: create_goal",
            contract.check_contract(self.root),
        )

    def test_external_gate_lifecycle_cli_is_required_in_supervisor_contract(self) -> None:
        target = "docs/acceptance/project-supervisor.md"
        expected_markers = (
            "--claim-external",
            "--authorization-json",
            "--block-external",
            "--reason-json",
        )
        required_markers = contract.REQUIRED_MARKERS[target]
        for marker in expected_markers:
            with self.subTest(marker=marker, phase="configured"):
                self.assertIn(marker, required_markers)

        original = (self.root / target).read_text(encoding="utf-8")
        for marker in expected_markers:
            with self.subTest(marker=marker, phase="enforced"):
                self._write(target, original.replace(marker, "removed-marker"))
                self.assertIn(
                    f"{target}: marker missing: {marker}",
                    contract.check_contract(self.root),
                )
        self._write(target, original)


if __name__ == "__main__":
    unittest.main()
