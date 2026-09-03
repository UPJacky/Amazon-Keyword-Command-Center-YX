import unittest
from unittest.mock import patch
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]


class UatOrchestrationContractTests(unittest.TestCase):
    def test_uat_runs_all_gates_and_has_timeout(self):
        source = (ROOT / "scripts" / "run_uat.py").read_text(encoding="utf-8")
        self.assertIn("DEFAULT_GATE_TIMEOUT_SECONDS = 120", source)
        self.assertIn("timeout=timeout", source)
        self.assertIn("check_worker_loops.py", source)
        self.assertIn("scripts.test_continuous_execution", source)
        self.assertIn("scripts.test_project_supervisor", source)
        self.assertIn("phase8_audit.py", source)
        self.assertIn("build_pages_demo.py", source)
        self.assertIn("required_counts_present", source)
        self.assertIn("EXPECTED_GATE_COUNT = 20", source)
        self.assertIn("gate_count_ok", source)
        self.assertIn("STRUCTURED_SUMMARY_GATES", source)
        self.assertIn("structured_summary_missing", source)

    def test_all_gates_use_the_same_bounded_timeout(self):
        sys.path.insert(0, str(ROOT))
        from scripts import run_uat

        calls = []

        def fake_run(command, timeout=run_uat.DEFAULT_GATE_TIMEOUT_SECONDS):
            calls.append((command, timeout))
            command_text = " ".join(command)
            counts = [139] if "worker/tests" in command_text else ([5] if "-s frontend" in command_text else [])
            summary = None
            if any(marker in command_text for marker in run_uat.STRUCTURED_SUMMARY_GATES):
                summary = {"network_calls": 0, "external_calls": 0, "local_only": True}
            return {"command": command, "passed": True, "timed_out": False, "test_counts": counts, "summary": summary, "stdout_tail": "", "stderr_tail": ""}

        with patch.object(run_uat, "run", side_effect=fake_run), patch("builtins.print"):
            result = run_uat.main()

        self.assertEqual(result, 0)
        self.assertEqual(len(calls), run_uat.EXPECTED_GATE_COUNT)
        self.assertEqual({timeout for _, timeout in calls}, {run_uat.DEFAULT_GATE_TIMEOUT_SECONDS})

    def test_uat_requires_local_only_zero_external_calls(self):
        sys.path.insert(0, str(ROOT))
        from scripts import run_uat

        self.assertEqual(run_uat.EXPECTED_GATE_COUNT, 20)
        with patch.object(run_uat, "run", return_value={"command": [], "passed": True, "timed_out": False, "test_counts": [], "stdout_tail": "", "stderr_tail": ""}), patch("builtins.print"):
            result = run_uat.main()
        self.assertEqual(result, 1)

    def test_uat_uses_cleanup_managed_temporary_roots(self):
        source = (ROOT / "scripts" / "run_uat.py").read_text(encoding="utf-8")
        self.assertIn("TemporaryDirectory", source)
        self.assertIn("ExitStack", source)
        self.assertIn("enter_context", source)

    def test_all_temporary_roots_exit_after_gate_collection(self):
        sys.path.insert(0, str(ROOT))
        from scripts import run_uat

        contexts = []

        class TrackingTemporaryDirectory:
            def __init__(self, prefix=""):
                self.path = str(ROOT / "__uat-test-temp__" / prefix)
                self.exited = False
                contexts.append(self)

            def __enter__(self):
                return self.path

            def __exit__(self, exc_type, exc, tb):
                self.exited = True
                return False

        def fake_run(command, timeout=run_uat.DEFAULT_GATE_TIMEOUT_SECONDS):
            command_text = " ".join(command)
            counts = [139] if "worker/tests" in command_text else ([5] if "-s frontend" in command_text else [])
            summary = {"network_calls": 0, "external_calls": 0, "local_only": True} if any(marker in command_text for marker in run_uat.STRUCTURED_SUMMARY_GATES) else None
            return {"command": command, "passed": True, "timed_out": False, "test_counts": counts, "summary": summary, "stdout_tail": "", "stderr_tail": ""}

        with patch.object(run_uat.tempfile, "TemporaryDirectory", side_effect=TrackingTemporaryDirectory), patch.object(run_uat, "run", side_effect=fake_run), patch("builtins.print"):
            result = run_uat.main()

        self.assertEqual(result, 0)
        self.assertEqual(len(contexts), 5)
        self.assertTrue(all(context.exited for context in contexts))

    def test_uat_rejects_gate_reported_external_calls(self):
        sys.path.insert(0, str(ROOT))
        from scripts import run_uat

        def fake_run(command, timeout=120):
            command_text = " ".join(command)
            counts = [116] if "worker/tests" in command_text else ([5] if "-s frontend" in command_text else [])
            summary = {"network_calls": 1, "external_calls": 0, "local_only": True} if "phase8_audit.py" in command_text else None
            return {"command": command, "passed": True, "timed_out": False, "test_counts": counts, "summary": summary, "stdout_tail": "", "stderr_tail": ""}

        with patch.object(run_uat, "run", side_effect=fake_run), patch("builtins.print"):
            result = run_uat.main()
        self.assertEqual(result, 1)

    def test_uat_rejects_malformed_summary_without_aborting_gate_collection(self):
        sys.path.insert(0, str(ROOT))
        from scripts import run_uat

        calls = []

        def fake_run(command, timeout=120):
            calls.append(command)
            command_text = " ".join(command)
            counts = [116] if "worker/tests" in command_text else ([5] if "-s frontend" in command_text else [])
            summary = {"network_calls": "unexpected", "external_calls": 0, "local_only": True}
            return {"command": command, "passed": True, "timed_out": False, "test_counts": counts, "summary": summary, "stdout_tail": "", "stderr_tail": ""}

        with patch.object(run_uat, "run", side_effect=fake_run), patch("builtins.print"):
            result = run_uat.main()

        self.assertEqual(result, 1)
        self.assertEqual(len(calls), run_uat.EXPECTED_GATE_COUNT)

    def test_summary_metrics_rejects_boolean_and_negative_counters(self):
        sys.path.insert(0, str(ROOT))
        from scripts import run_uat

        network, external, local_only, errors = run_uat._summary_metrics([
            {"command": ["gate"], "summary": {"network_calls": True, "external_calls": -1, "local_only": "yes"}}
        ])
        self.assertEqual((network, external, local_only), (0, 0, True))
        self.assertEqual(len(errors), 3)

    def test_summary_metrics_ignores_missing_summary_without_raising(self):
        sys.path.insert(0, str(ROOT))
        from scripts import run_uat

        self.assertEqual(
            run_uat._summary_metrics([{"command": ["missing-summary"], "summary": None}]),
            (0, 0, True, []),
        )

    def test_uat_rejects_missing_structured_summary_for_boundary_gates(self):
        sys.path.insert(0, str(ROOT))
        from scripts import run_uat

        def fake_run(command, timeout=120):
            command_text = " ".join(command)
            counts = [116] if "worker/tests" in command_text else ([5] if "-s frontend" in command_text else [])
            summary = None
            if "check_worker_loops.py" not in command_text and "phase8_audit.py" not in command_text and "build_pages_demo.py" not in command_text:
                summary = {"network_calls": 0, "external_calls": 0, "local_only": True}
            return {"command": command, "passed": True, "timed_out": False, "test_counts": counts, "summary": summary, "stdout_tail": "", "stderr_tail": ""}

        with patch.object(run_uat, "run", side_effect=fake_run), patch("builtins.print"):
            result = run_uat.main()
        self.assertEqual(result, 1)

    def test_missing_structured_summary_is_recorded_in_summary_contract_errors(self):
        sys.path.insert(0, str(ROOT))
        from scripts import run_uat

        def fake_run(command, timeout=120):
            command_text = " ".join(command)
            counts = [140] if "worker/tests" in command_text else ([5] if "-s frontend" in command_text else [])
            return {
                "command": command,
                "passed": True,
                "timed_out": False,
                "test_counts": counts,
                "summary": None,
                "stdout_tail": "",
                "stderr_tail": "",
            }

        printed = []
        with patch.object(run_uat, "run", side_effect=fake_run), patch("builtins.print", side_effect=printed.append):
            result = run_uat.main()

        self.assertEqual(result, 1)
        report = __import__("json").loads(printed[-1])
        self.assertTrue(any("missing structured summary" in error for error in report["summary_contract_errors"]))
        self.assertTrue(report["structured_summary_missing"])

    def test_uat_rejects_partial_structured_summary_without_aborting_gate_collection(self):
        sys.path.insert(0, str(ROOT))
        from scripts import run_uat

        calls = []

        def fake_run(command, timeout=120):
            calls.append(command)
            command_text = " ".join(command)
            counts = [116] if "worker/tests" in command_text else ([5] if "-s frontend" in command_text else [])
            summary = {"network_calls": 0, "external_calls": 0} if "phase8_audit.py" in command_text else None
            return {"command": command, "passed": True, "timed_out": False, "test_counts": counts, "summary": summary, "stdout_tail": "", "stderr_tail": ""}

        with patch.object(run_uat, "run", side_effect=fake_run), patch("builtins.print"):
            result = run_uat.main()

        self.assertEqual(result, 1)
        self.assertEqual(len(calls), run_uat.EXPECTED_GATE_COUNT)

    def test_unittest_pages_gate_does_not_require_process_summary(self):
        sys.path.insert(0, str(ROOT))
        from scripts import run_uat

        command = ["python", "-m", "unittest", "scripts/test_build_pages_demo.py", "-v"]
        self.assertNotIn(command[-2], run_uat.STRUCTURED_SUMMARY_GATES)

    def test_loop_gate_requires_bounded_summary_not_only_exit_code(self):
        source = (ROOT / "scripts" / "check_worker_loops.py").read_text(encoding="utf-8")
        self.assertIn('summary.get("cycles") == 2', source)
        self.assertIn('summary.get("errors") == 0', source)
        self.assertIn('summary.get("stopped") is False', source)
        self.assertIn("heartbeats >= 2", source)
        self.assertIn("KWCC_LOOP_TIMEOUT_SECONDS", source)
        self.assertIn('gate_count_ok = len(results) == 2', source)

    def test_gate_start_failure_is_normalized_and_does_not_raise(self):
        sys.path.insert(0, str(ROOT))
        from scripts import run_uat

        with patch.object(subprocess, "run", side_effect=OSError("missing runtime")):
            result = run_uat.run(["missing-runtime"])
        self.assertFalse(result["passed"])
        self.assertIn("unable to start gate", result["stderr_tail"])

    def test_gate_timeout_is_normalized_and_does_not_raise(self):
        sys.path.insert(0, str(ROOT))
        from scripts import run_uat

        with patch.object(subprocess, "run", side_effect=subprocess.TimeoutExpired(["slow"], 1)):
            result = run_uat.run(["slow"], timeout=1)
        self.assertFalse(result["passed"])
        self.assertTrue(result["timed_out"])

    def test_unexpected_gate_exception_is_normalized_and_does_not_stop_collection(self):
        sys.path.insert(0, str(ROOT))
        from scripts import run_uat

        with patch.object(run_uat, "run", side_effect=RuntimeError("gate exploded")):
            result = run_uat.run_gate(["broken-gate"], timeout=1)
        self.assertFalse(result["passed"])
        self.assertEqual(result["exception_type"], "RuntimeError")
        self.assertIn("gate exploded", result["stderr_tail"])

    def test_uat_continues_after_unexpected_gate_exception(self):
        sys.path.insert(0, str(ROOT))
        from scripts import run_uat

        calls = []

        def fake_run(command, timeout=120):
            calls.append(command)
            if len(calls) == 1:
                raise RuntimeError("first gate exploded")
            command_text = " ".join(command)
            counts = [142] if "worker/tests" in command_text else ([5] if "-s frontend" in command_text else [])
            summary = {"network_calls": 0, "external_calls": 0, "local_only": True} if any(marker in command_text for marker in run_uat.STRUCTURED_SUMMARY_GATES) else None
            return {"command": command, "passed": True, "timed_out": False, "test_counts": counts, "summary": summary, "stdout_tail": "", "stderr_tail": ""}

        with patch.object(run_uat, "run", side_effect=fake_run), patch("builtins.print"):
            result = run_uat.main()

        self.assertEqual(result, 1)
        self.assertEqual(len(calls), run_uat.EXPECTED_GATE_COUNT)

    def test_worker_loop_normalizes_unexpected_supervisor_exception(self):
        sys.path.insert(0, str(ROOT))
        from scripts import run_worker_loop

        argv = ["run_worker_loop.py", "--queue-root", "queue", "--storage-root", "storage", "--max-cycles", "1"]
        with patch.object(sys, "argv", argv), patch.object(run_worker_loop, "run_loop", side_effect=RuntimeError("supervisor exploded")), patch("builtins.print") as printed:
            result = run_worker_loop.main()

        self.assertEqual(result, 1)
        payload = __import__("json").loads(printed.call_args.args[0])
        self.assertEqual(payload["errors"], 1)
        self.assertEqual(payload["reason"], "unexpected_supervisor_exception")

    def test_powershell_loop_normalizes_wrapper_start_failure(self):
        source = (ROOT / "scripts" / "run_worker_loop.ps1").read_text(encoding="utf-8")
        self.assertIn("catch {", source)
        self.assertIn("ConvertTo-Json", source)
        self.assertIn("unexpected_supervisor_exception", source)

    def test_worker_loop_start_failure_is_normalized(self):
        sys.path.insert(0, str(ROOT))
        from scripts import check_worker_loops

        with patch.object(subprocess, "run", side_effect=OSError("missing loop runtime")):
            result = check_worker_loops.run(["missing-loop-runtime"])
        self.assertFalse(result["passed"])
        self.assertIn("unable to start loop gate", result["stderr_tail"])

    def test_uat_continues_collecting_gates_after_a_failure(self):
        sys.path.insert(0, str(ROOT))
        from scripts import run_uat

        calls = []

        def fake_run(command, timeout=120):
            calls.append(command)
            command_text = " ".join(command)
            counts = [116] if "worker/tests" in command_text else ([5] if "-s frontend" in command_text else [])
            return {
                "command": command,
                "passed": len(calls) != 1,
                "timed_out": False,
                "test_counts": counts,
                "stdout_tail": "",
                "stderr_tail": "",
            }

        with patch.object(run_uat, "run", side_effect=fake_run), patch("builtins.print"):
            result = run_uat.main()

        self.assertEqual(result, 1)
        self.assertEqual(len(calls), run_uat.EXPECTED_GATE_COUNT)
        self.assertTrue(any("phase8_audit.py" in part for command in calls for part in command))
        self.assertTrue(any("test_build_pages_demo.py" in part for command in calls for part in command))


class DocumentationSnapshotTests(unittest.TestCase):
    def test_memory_counts_require_unique_current_section(self):
        from scripts.check_phase8_documentation import memory_counts_match
        snapshot = {"worker": "200", "frontend": "8"}
        current = "## 当前验证快照\nWorker 200 项、前端 8 项\n"
        self.assertTrue(memory_counts_match(current + "## 历史\nWorker 144 项、前端 5 项", snapshot))
        self.assertFalse(memory_counts_match("## 历史\nWorker 200 项、前端 8 项", snapshot))
        self.assertFalse(memory_counts_match(current + current, snapshot))
        self.assertFalse(memory_counts_match(current.replace("200", "144"), snapshot))

    def test_current_plan_heading_accepts_new_date_but_not_duplicates(self):
        from scripts.check_phase8_documentation import current_state_section
        current = "### 当前执行状态（2026-08-31）\nverified\n### 下一步\nnext"
        self.assertEqual("verified", current_state_section(current))
        self.assertIsNone(current_state_section(current + "\n### 当前执行状态（2026-08-21）\nold"))

    def test_document_date_is_valid_top_metadata_not_historical_text(self):
        from scripts.check_phase8_documentation import has_valid_update_date
        self.assertTrue(has_valid_update_date("---\nupdated_at: 2026-08-31\n---\n# Current"))
        self.assertFalse(has_valid_update_date("updated_at: 2026-02-30\n# Current"))
        self.assertFalse(has_valid_update_date("# History\nupdated_at: 2026-08-31"))


if __name__ == "__main__":
    unittest.main()
