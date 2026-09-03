from __future__ import annotations

import copy
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from scripts import project_supervisor as supervisor


def make_task(
    task_id: str,
    *,
    status: str = "pending",
    execution: str = "local",
    depends_on: list[str] | None = None,
    fingerprint_material: str = "input-v1",
    input_fingerprint: str | None = None,
    verified_fingerprint: str = "",
    verification: object | None = None,
) -> dict[str, object]:
    fingerprint_inputs = [{"kind": "literal", "value": fingerprint_material}]
    if verification is None:
        verification = [
            {
                "kind": "unit",
                "source": "test",
                "result": "passed",
                "summary": "verified",
            }
        ] if status == "completed" else []
    task = {
        "id": task_id,
        "title": f"Task {task_id}",
        "status": status,
        "execution": execution,
        "depends_on": [] if depends_on is None else depends_on,
        "fingerprint_inputs": fingerprint_inputs,
        "input_fingerprint": "",
        "verified_fingerprint": verified_fingerprint,
        "acceptance": ["expected result"],
        "verification": verification,
    }
    current_fingerprint = supervisor.compute_task_fingerprint(task, ".")
    task["input_fingerprint"] = (
        current_fingerprint if input_fingerprint is None else input_fingerprint
    )
    if status == "completed" and not verified_fingerprint:
        task["verified_fingerprint"] = task["input_fingerprint"]
    return task


def make_ledger(*tasks: dict[str, object]) -> dict[str, object]:
    return {"schema_version": 1, "tasks": list(tasks)}


def authorization_receipts() -> list[dict[str, str]]:
    return [
        {
            "kind": "authorization",
            "source": "explicit user authorization",
            "result": "passed",
            "summary": "temporary external Gate work approved",
        }
    ]


def external_block_receipts() -> list[dict[str, str]]:
    return [
        {
            "kind": "external_block",
            "source": "external Gate attempt",
            "result": "passed",
            "summary": "provider remained unavailable after bounded attempts",
        }
    ]


class ProjectSupervisorTests(unittest.TestCase):
    def test_dependencies_gate_tasks_and_ledger_order_selects_next(self) -> None:
        ledger = make_ledger(
            make_task("foundation", status="completed"),
            make_task("dependent", depends_on=["foundation"]),
            make_task("parallel"),
        )

        result = supervisor.analyze_ledger(ledger)

        self.assertEqual("RUNNING", result["execution_state"])
        self.assertEqual(["foundation"], result["effective_completed"])
        self.assertEqual(["dependent", "parallel"], result["runnable"])
        self.assertEqual("dependent", result["next_task"]["id"])

    def test_unmet_dependency_leaves_only_prerequisite_runnable(self) -> None:
        ledger = make_ledger(
            make_task("dependent", depends_on=["foundation"]),
            make_task("foundation"),
        )

        result = supervisor.analyze_ledger(ledger)

        self.assertEqual(["foundation"], result["runnable"])
        self.assertEqual("foundation", result["next_task_id"])

    def test_valid_completed_task_is_deduplicated(self) -> None:
        ledger = make_ledger(
            make_task("already-done", status="completed"),
            make_task("new-work"),
        )

        result = supervisor.analyze_ledger(ledger)

        self.assertEqual(["already-done"], result["effective_completed"])
        self.assertEqual([], result["stale"])
        self.assertEqual("new-work", result["next_task_id"])

    def test_changed_fingerprint_reopens_completed_task_as_stale(self) -> None:
        old_task = make_task("changed", fingerprint_material="input-v1")
        ledger = make_ledger(
            make_task(
                "changed",
                status="completed",
                fingerprint_material="input-v2",
                input_fingerprint=old_task["input_fingerprint"],
                verified_fingerprint=old_task["input_fingerprint"],
                verification=[
                    {
                        "kind": "unit",
                        "source": "old tests",
                        "result": "passed",
                        "summary": "old inputs verified",
                    }
                ],
            ),
            make_task("later"),
        )

        result = supervisor.analyze_ledger(ledger)

        self.assertEqual(["changed"], result["stale"])
        self.assertEqual(["changed", "later"], result["runnable"])
        self.assertEqual("changed", result["next_task_id"])
        self.assertTrue(result["next_task"]["stale"])

    def test_empty_verification_reopens_completed_task_as_stale(self) -> None:
        task = make_task("unverified", status="completed", verification=[])

        result = supervisor.analyze_ledger(make_ledger(task))

        self.assertEqual("RUNNING", result["execution_state"])
        self.assertEqual(["unverified"], result["stale"])
        self.assertEqual("unverified", result["next_task_id"])

    def test_external_work_without_local_work_blocks_externally(self) -> None:
        ledger = make_ledger(
            make_task("local-done", status="completed"),
            make_task("deploy", execution="external", depends_on=["local-done"]),
        )

        result = supervisor.analyze_ledger(ledger)

        self.assertEqual("BLOCKED_EXTERNAL", result["execution_state"])
        self.assertEqual(["deploy"], result["blocked_external"])
        self.assertIsNone(result["next_task"])

    def test_only_risk_blocker_returns_blocked_risk(self) -> None:
        ledger = make_ledger(make_task("dangerous", status="blocked_risk"))

        result = supervisor.analyze_ledger(ledger)

        self.assertEqual("BLOCKED_RISK", result["execution_state"])
        self.assertEqual(["dangerous"], result["blocked_risk"])

    def test_external_blocker_takes_precedence_over_risk_blocker(self) -> None:
        ledger = make_ledger(
            make_task("risk", status="blocked_risk"),
            make_task("credentials", status="blocked_external", execution="external"),
        )

        result = supervisor.analyze_ledger(ledger)

        self.assertEqual("BLOCKED_EXTERNAL", result["execution_state"])
        self.assertEqual(["credentials"], result["blocked_external"])
        self.assertEqual(["risk"], result["blocked_risk"])

    def test_all_effectively_completed_returns_project_complete(self) -> None:
        ledger = make_ledger(
            make_task("one", status="completed"),
            make_task("two", status="completed", depends_on=["one"]),
        )

        result = supervisor.analyze_ledger(ledger)

        self.assertEqual("PROJECT_COMPLETE", result["execution_state"])
        self.assertIsNone(result["next_task"])

    def test_local_running_task_keeps_supervisor_running(self) -> None:
        ledger = make_ledger(make_task("active", status="running"))

        result = supervisor.analyze_ledger(ledger)

        self.assertEqual("RUNNING", result["execution_state"])
        self.assertEqual(["active"], result["running"])
        self.assertEqual("active", result["next_task_id"])

    def test_multiple_running_tasks_are_rejected(self) -> None:
        ledger = make_ledger(
            make_task("first", status="running"),
            make_task("second", status="running"),
        )
        with self.assertRaises(supervisor.LedgerValidationError) as caught:
            supervisor.analyze_ledger(ledger)
        self.assertTrue(any("multiple running tasks" in error for error in caught.exception.errors))

    def test_running_task_requires_effectively_completed_dependencies(self) -> None:
        ledger = make_ledger(
            make_task("dependency"),
            make_task("active", status="running", depends_on=["dependency"]),
        )
        with self.assertRaises(supervisor.LedgerValidationError) as caught:
            supervisor.analyze_ledger(ledger)
        self.assertIn(
            "running task 'active' has unsatisfied dependencies",
            caught.exception.errors,
        )

    def test_path_fingerprint_change_reopens_completed_task(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "source.txt"
            source.write_text("v1", encoding="utf-8")
            task = make_task("watched", status="completed")
            task["fingerprint_inputs"] = [{"kind": "path", "path": "source.txt"}]
            first = supervisor.compute_task_fingerprint(task, root)
            task["input_fingerprint"] = first
            task["verified_fingerprint"] = first
            self.assertEqual("PROJECT_COMPLETE", supervisor.analyze_ledger(make_ledger(task), root)["execution_state"])

            source.write_text("v2", encoding="utf-8")
            result = supervisor.analyze_ledger(make_ledger(task), root)
            self.assertEqual("RUNNING", result["execution_state"])
            self.assertEqual(["watched"], result["stale"])

    def test_acceptance_change_reopens_completed_task(self) -> None:
        task = make_task("contract", status="completed")
        self.assertEqual(
            "PROJECT_COMPLETE",
            supervisor.analyze_ledger(make_ledger(task))["execution_state"],
        )

        task["acceptance"].append("new required behavior")
        result = supervisor.analyze_ledger(make_ledger(task))

        self.assertEqual("RUNNING", result["execution_state"])
        self.assertEqual(["contract"], result["stale"])

    def test_dependency_change_reopens_completed_task(self) -> None:
        foundation = make_task("foundation", status="completed")
        task = make_task("contract", status="completed")
        ledger = make_ledger(foundation, task)
        self.assertEqual(
            "PROJECT_COMPLETE", supervisor.analyze_ledger(ledger)["execution_state"]
        )

        task["depends_on"] = ["foundation"]
        result = supervisor.analyze_ledger(ledger)

        self.assertEqual("RUNNING", result["execution_state"])
        self.assertEqual(["contract"], result["stale"])

    def test_malformed_persisted_receipt_is_rejected(self) -> None:
        task = make_task("bad-receipt", status="completed")
        task["verification"] = [{"result": "passed"}]

        with self.assertRaises(supervisor.LedgerValidationError) as caught:
            supervisor.analyze_ledger(make_ledger(task))

        self.assertTrue(
            any("verification[0].kind" in error for error in caught.exception.errors)
        )

    def test_analysis_does_not_mutate_ledger(self) -> None:
        ledger = make_ledger(make_task("work"))
        original = copy.deepcopy(ledger)

        supervisor.analyze_ledger(ledger)

        self.assertEqual(original, ledger)

    def test_claim_marks_selected_task_running_and_is_idempotent(self) -> None:
        ledger = make_ledger(make_task("first"), make_task("second"))

        first_decision, first_changed = supervisor.claim_next_task(ledger)
        second_decision, second_changed = supervisor.claim_next_task(ledger)

        self.assertTrue(first_changed)
        self.assertFalse(second_changed)
        self.assertEqual("running", ledger["tasks"][0]["status"])
        self.assertEqual("first", first_decision["next_task_id"])
        self.assertEqual("first", second_decision["next_task_id"])

    def test_claim_refreshes_running_task_after_inputs_change(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "source.txt"
            source.write_text("v1", encoding="utf-8")
            task = make_task("active", status="running")
            task["fingerprint_inputs"] = [{"kind": "path", "path": "source.txt"}]
            task["input_fingerprint"] = supervisor.compute_task_fingerprint(task, root)
            source.write_text("v2", encoding="utf-8")

            decision, changed = supervisor.claim_next_task(make_ledger(task), root)

        self.assertTrue(changed)
        self.assertEqual(
            decision["current_fingerprints"]["active"], task["input_fingerprint"]
        )

    def test_generic_claim_never_claims_a_ready_external_task(self) -> None:
        ledger = make_ledger(
            make_task("first", status="blocked_external", execution="external"),
            make_task("second", status="pending", execution="external"),
        )
        original = copy.deepcopy(ledger)

        decision, changed = supervisor.claim_next_task(ledger)

        self.assertFalse(changed)
        self.assertEqual("BLOCKED_EXTERNAL", decision["execution_state"])
        self.assertEqual(original, ledger)

    def test_generic_claim_does_not_refresh_external_running_task(self) -> None:
        task = make_task(
            "external-active",
            status="running",
            execution="external",
            verification=authorization_receipts(),
        )
        claimed_fingerprint = task["input_fingerprint"]
        task["fingerprint_inputs"][0]["value"] = "input-v2"
        claimed_receipts = copy.deepcopy(task["verification"])
        ledger = make_ledger(task)

        decision, changed = supervisor.claim_next_task(ledger)

        self.assertFalse(changed)
        self.assertEqual("RUNNING", decision["execution_state"])
        self.assertNotEqual(
            decision["current_fingerprints"]["external-active"],
            claimed_fingerprint,
        )
        self.assertEqual(claimed_fingerprint, task["input_fingerprint"])
        self.assertEqual(claimed_receipts, task["verification"])

    def test_claim_external_task_uses_explicit_id_and_not_ledger_order(self) -> None:
        ledger = make_ledger(
            make_task("first", status="blocked_external", execution="external"),
            make_task("second", status="blocked_external", execution="external"),
        )
        receipts = authorization_receipts()

        decision = supervisor.claim_external_task(ledger, "second", receipts)

        first, second = ledger["tasks"]
        self.assertEqual("blocked_external", first["status"])
        self.assertEqual([], first["verification"])
        self.assertEqual("running", second["status"])
        self.assertEqual(receipts, second["verification"])
        self.assertEqual("", second["verified_fingerprint"])
        self.assertEqual(
            decision["current_fingerprints"]["second"],
            second["input_fingerprint"],
        )
        self.assertEqual("second", decision["next_task_id"])

    def test_claim_external_task_accepts_blocked_pending_and_stale_completed(self) -> None:
        old = make_task("old", execution="external", fingerprint_material="input-v1")
        for status in ("blocked_external", "pending", "completed"):
            with self.subTest(status=status):
                task = make_task(
                    "deploy",
                    status=status,
                    execution="external",
                    fingerprint_material="input-v2",
                    input_fingerprint=old["input_fingerprint"],
                    verified_fingerprint=old["input_fingerprint"],
                )
                ledger = make_ledger(task)

                decision = supervisor.claim_external_task(
                    ledger,
                    "deploy",
                    authorization_receipts(),
                )

                self.assertEqual("running", task["status"])
                self.assertEqual("", task["verified_fingerprint"])
                self.assertNotEqual(old["input_fingerprint"], task["input_fingerprint"])
                self.assertEqual(
                    decision["current_fingerprints"]["deploy"],
                    task["input_fingerprint"],
                )

    def test_claim_external_task_rejects_unknown_local_and_wrong_status(self) -> None:
        cases = (
            (make_ledger(make_task("deploy", execution="external")), "missing"),
            (make_ledger(make_task("local")), "local"),
            (
                make_ledger(
                    make_task("deploy", status="completed", execution="external")
                ),
                "deploy",
            ),
            (
                make_ledger(
                    make_task(
                        "deploy",
                        status="running",
                        execution="external",
                        verification=authorization_receipts(),
                    )
                ),
                "deploy",
            ),
            (
                make_ledger(
                    make_task(
                        "deploy",
                        status="blocked_risk",
                        execution="external",
                    )
                ),
                "deploy",
            ),
        )
        for ledger, task_id in cases:
            with self.subTest(task_id=task_id, status=ledger["tasks"][0]["status"]):
                original = copy.deepcopy(ledger)
                with self.assertRaises(supervisor.LedgerValidationError):
                    supervisor.claim_external_task(
                        ledger,
                        task_id,
                        authorization_receipts(),
                    )
                self.assertEqual(original, ledger)

    def test_claim_external_task_rejects_unmet_dependencies_or_existing_running(self) -> None:
        cases = (
            make_ledger(
                make_task("foundation"),
                make_task(
                    "deploy",
                    status="blocked_external",
                    execution="external",
                    depends_on=["foundation"],
                ),
            ),
            make_ledger(
                make_task("active", status="running"),
                make_task("deploy", status="blocked_external", execution="external"),
            ),
        )
        for ledger in cases:
            with self.subTest(tasks=[task["id"] for task in ledger["tasks"]]):
                original = copy.deepcopy(ledger)
                with self.assertRaises(supervisor.LedgerValidationError):
                    supervisor.claim_external_task(
                        ledger,
                        "deploy",
                        authorization_receipts(),
                    )
                self.assertEqual(original, ledger)

    def test_claim_external_task_requires_structured_passed_authorization_receipts(self) -> None:
        invalid_receipts = (
            None,
            [],
            [{"kind": "authorization", "source": "user", "result": "passed"}],
            [
                {
                    "kind": "authorization",
                    "source": "user",
                    "result": "failed",
                    "summary": "not approved",
                }
            ],
            [
                {
                    "kind": "unit",
                    "source": "tests",
                    "result": "passed",
                    "summary": "not an authorization event",
                }
            ],
            [
                {
                    "kind": "authorization",
                    "source": "user",
                    "result": "passed",
                    "summary": "approved",
                    "credential": "redacted",
                }
            ],
        )
        for receipts in invalid_receipts:
            with self.subTest(receipts=receipts):
                ledger = make_ledger(
                    make_task(
                        "deploy",
                        status="blocked_external",
                        execution="external",
                    )
                )
                original = copy.deepcopy(ledger)
                with self.assertRaises(supervisor.LedgerValidationError):
                    supervisor.claim_external_task(ledger, "deploy", receipts)
                self.assertEqual(original, ledger)

    def test_repeated_explicit_external_claim_is_rejected(self) -> None:
        ledger = make_ledger(
            make_task("deploy", status="blocked_external", execution="external")
        )
        supervisor.claim_external_task(ledger, "deploy", authorization_receipts())
        claimed = copy.deepcopy(ledger)

        with self.assertRaises(supervisor.LedgerValidationError):
            supervisor.claim_external_task(ledger, "deploy", authorization_receipts())

        self.assertEqual(claimed, ledger)

    def test_block_external_task_replaces_authorization_with_auditable_event(self) -> None:
        task = make_task(
            "deploy",
            status="running",
            execution="external",
            verification=authorization_receipts(),
        )
        task["verified_fingerprint"] = task["input_fingerprint"]
        ledger = make_ledger(task)
        receipts = external_block_receipts()

        decision = supervisor.block_external_task(ledger, "deploy", receipts)

        self.assertEqual("blocked_external", task["status"])
        self.assertEqual("", task["verified_fingerprint"])
        self.assertEqual(receipts, task["verification"])
        self.assertEqual("external_block", task["verification"][0]["kind"])
        self.assertEqual("passed", task["verification"][0]["result"])
        self.assertEqual("BLOCKED_EXTERNAL", decision["execution_state"])

    def test_block_external_task_rejects_unknown_local_and_nonrunning_tasks(self) -> None:
        cases = (
            (make_ledger(make_task("deploy", execution="external")), "missing"),
            (make_ledger(make_task("local", status="running")), "local"),
            (make_ledger(make_task("deploy", execution="external")), "deploy"),
            (
                make_ledger(
                    make_task(
                        "deploy",
                        status="blocked_external",
                        execution="external",
                    )
                ),
                "deploy",
            ),
            (
                make_ledger(
                    make_task("deploy", status="completed", execution="external")
                ),
                "deploy",
            ),
        )
        for ledger, task_id in cases:
            with self.subTest(task_id=task_id, status=ledger["tasks"][0]["status"]):
                original = copy.deepcopy(ledger)
                with self.assertRaises(supervisor.LedgerValidationError):
                    supervisor.block_external_task(
                        ledger,
                        task_id,
                        external_block_receipts(),
                    )
                self.assertEqual(original, ledger)

    def test_block_external_task_requires_structured_passed_event_receipts(self) -> None:
        invalid_receipts = (
            None,
            [],
            [
                {
                    "kind": "external_block",
                    "source": "attempt",
                    "result": "failed",
                    "summary": "not an auditable passed event",
                }
            ],
            [
                {
                    "kind": "authorization",
                    "source": "user",
                    "result": "passed",
                    "summary": "wrong lifecycle event",
                }
            ],
        )
        for receipts in invalid_receipts:
            with self.subTest(receipts=receipts):
                ledger = make_ledger(
                    make_task(
                        "deploy",
                        status="running",
                        execution="external",
                        verification=authorization_receipts(),
                    )
                )
                original = copy.deepcopy(ledger)
                with self.assertRaises(supervisor.LedgerValidationError):
                    supervisor.block_external_task(ledger, "deploy", receipts)
                self.assertEqual(original, ledger)

    def test_external_task_success_reuses_complete_task(self) -> None:
        ledger = make_ledger(
            make_task("deploy", status="blocked_external", execution="external")
        )
        supervisor.claim_external_task(ledger, "deploy", authorization_receipts())
        completion = [
            {
                "kind": "integration",
                "source": "external Gate",
                "result": "passed",
                "summary": "external acceptance matrix passed",
            }
        ]

        decision = supervisor.complete_task(ledger, "deploy", completion)

        task = ledger["tasks"][0]
        self.assertEqual("completed", task["status"])
        self.assertEqual(task["input_fingerprint"], task["verified_fingerprint"])
        self.assertEqual(completion, task["verification"])
        self.assertEqual("PROJECT_COMPLETE", decision["execution_state"])

    def test_complete_task_claims_successor_in_same_transition(self) -> None:
        ledger = make_ledger(make_task("first"), make_task("second", depends_on=["first"]))
        supervisor.claim_next_task(ledger)
        receipt = [{"kind": "unit", "source": "tests", "result": "passed", "summary": "ok"}]

        decision = supervisor.complete_task(ledger, "first", receipt)

        self.assertEqual("completed", ledger["tasks"][0]["status"])
        self.assertEqual(ledger["tasks"][0]["input_fingerprint"], ledger["tasks"][0]["verified_fingerprint"])
        self.assertEqual(receipt, ledger["tasks"][0]["verification"])
        self.assertEqual("running", ledger["tasks"][1]["status"])
        self.assertEqual("second", decision["next_task_id"])

    def test_complete_task_returns_external_block_without_claiming_it(self) -> None:
        ledger = make_ledger(
            make_task("local", status="running"),
            make_task("deploy", status="blocked_external", execution="external", depends_on=["local"]),
        )
        receipt = [{"kind": "unit", "source": "tests", "result": "passed", "summary": "ok"}]

        decision = supervisor.complete_task(ledger, "local", receipt)

        self.assertEqual("BLOCKED_EXTERNAL", decision["execution_state"])
        self.assertEqual("blocked_external", ledger["tasks"][1]["status"])

    def test_complete_task_rejects_inputs_changed_while_running(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "source.txt"
            source.write_text("v1", encoding="utf-8")
            task = make_task("active", status="running")
            task["fingerprint_inputs"] = [{"kind": "path", "path": "source.txt"}]
            task["input_fingerprint"] = supervisor.compute_task_fingerprint(task, root)
            source.write_text("v2", encoding="utf-8")
            receipt = [{"kind": "unit", "source": "tests", "result": "passed", "summary": "ok"}]

            with self.assertRaises(supervisor.LedgerValidationError) as caught:
                supervisor.complete_task(make_ledger(task), "active", receipt, root)

        self.assertTrue(any("inputs changed while running" in error for error in caught.exception.errors))

    def test_complete_task_requires_structured_passed_receipts(self) -> None:
        invalid_receipts = ([], [{"result": "passed"}], [{"kind": "unit", "source": "x", "result": "failed", "summary": "bad"}])
        for receipt in invalid_receipts:
            with self.subTest(receipt=receipt):
                ledger = make_ledger(make_task("active", status="running"))
                with self.assertRaises(supervisor.LedgerValidationError):
                    supervisor.complete_task(ledger, "active", receipt)

    def test_cli_claim_persists_running_task_atomically(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            ledger_path = Path(temp_dir) / "PROJECT_TASKS.json"
            ledger_path.write_text(json.dumps(make_ledger(make_task("work"))), encoding="utf-8")
            output = io.StringIO()

            with redirect_stdout(output):
                exit_code = supervisor.main(["--claim", str(ledger_path)])

            persisted = json.loads(ledger_path.read_text(encoding="utf-8"))
            payload = json.loads(output.getvalue())
            self.assertEqual(0, exit_code)
            self.assertEqual("running", persisted["tasks"][0]["status"])
            self.assertEqual("work", payload["next_task_id"])

    def test_cli_complete_persists_receipt_and_claims_successor(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            ledger_path = Path(temp_dir) / "PROJECT_TASKS.json"
            ledger = make_ledger(
                make_task("first", status="running"),
                make_task("second", depends_on=["first"]),
            )
            ledger_path.write_text(json.dumps(ledger), encoding="utf-8")
            receipt = [{"kind": "unit", "source": "tests", "result": "passed", "summary": "ok"}]
            output = io.StringIO()

            with redirect_stdout(output):
                exit_code = supervisor.main(
                    [
                        "--complete",
                        "first",
                        "--verification-json",
                        json.dumps(receipt),
                        str(ledger_path),
                    ]
                )

            persisted = json.loads(ledger_path.read_text(encoding="utf-8"))
            payload = json.loads(output.getvalue())
            self.assertEqual(0, exit_code)
            self.assertEqual("completed", persisted["tasks"][0]["status"])
            self.assertEqual(receipt, persisted["tasks"][0]["verification"])
            self.assertEqual("running", persisted["tasks"][1]["status"])
            self.assertEqual("second", payload["next_task_id"])

    def test_cli_claim_and_block_external_persist_lifecycle_receipts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            ledger_path = Path(temp_dir) / "PROJECT_TASKS.json"
            ledger_path.write_text(
                json.dumps(
                    make_ledger(
                        make_task(
                            "deploy",
                            status="blocked_external",
                            execution="external",
                        )
                    )
                ),
                encoding="utf-8",
            )
            claim_output = io.StringIO()
            authorization = authorization_receipts()

            with redirect_stdout(claim_output):
                claim_exit = supervisor.main(
                    [
                        "--claim-external",
                        "deploy",
                        "--authorization-json",
                        json.dumps(authorization),
                        str(ledger_path),
                    ]
                )

            claimed = json.loads(ledger_path.read_text(encoding="utf-8"))
            claim_payload = json.loads(claim_output.getvalue())
            self.assertEqual(0, claim_exit)
            self.assertEqual("RUNNING", claim_payload["execution_state"])
            self.assertEqual("running", claimed["tasks"][0]["status"])
            self.assertEqual(authorization, claimed["tasks"][0]["verification"])

            block_output = io.StringIO()
            block_event = external_block_receipts()
            with redirect_stdout(block_output):
                block_exit = supervisor.main(
                    [
                        "--block-external",
                        "deploy",
                        "--reason-json",
                        json.dumps(block_event),
                        str(ledger_path),
                    ]
                )

            blocked = json.loads(ledger_path.read_text(encoding="utf-8"))
            block_payload = json.loads(block_output.getvalue())
            self.assertEqual(0, block_exit)
            self.assertEqual("BLOCKED_EXTERNAL", block_payload["execution_state"])
            self.assertEqual("blocked_external", blocked["tasks"][0]["status"])
            self.assertEqual(block_event, blocked["tasks"][0]["verification"])
            self.assertEqual("", blocked["tasks"][0]["verified_fingerprint"])

    def test_cli_external_lifecycle_rejects_invalid_json_without_mutation(self) -> None:
        cases = (
            ("--claim-external", "--authorization-json"),
            ("--block-external", "--reason-json"),
        )
        for action, receipt_flag in cases:
            with self.subTest(action=action):
                with tempfile.TemporaryDirectory() as temp_dir:
                    ledger_path = Path(temp_dir) / "PROJECT_TASKS.json"
                    if action == "--claim-external":
                        task = make_task(
                            "deploy",
                            status="blocked_external",
                            execution="external",
                        )
                    else:
                        task = make_task(
                            "deploy",
                            status="running",
                            execution="external",
                            verification=authorization_receipts(),
                        )
                    ledger = make_ledger(task)
                    ledger_path.write_text(json.dumps(ledger), encoding="utf-8")
                    output = io.StringIO()

                    with redirect_stdout(output):
                        exit_code = supervisor.main(
                            [
                                action,
                                "deploy",
                                receipt_flag,
                                "{invalid-json",
                                str(ledger_path),
                            ]
                        )

                    payload = json.loads(output.getvalue())
                    persisted = json.loads(ledger_path.read_text(encoding="utf-8"))
                    self.assertNotEqual(0, exit_code)
                    self.assertEqual("INVALID", payload["execution_state"])
                    self.assertEqual(ledger, persisted)

    def test_cli_external_lifecycle_requires_matching_receipt_flag(self) -> None:
        cases = (
            (
                "--claim-external",
                make_task(
                    "deploy",
                    status="blocked_external",
                    execution="external",
                ),
            ),
            (
                "--block-external",
                make_task(
                    "deploy",
                    status="running",
                    execution="external",
                    verification=authorization_receipts(),
                ),
            ),
        )
        for action, task in cases:
            with self.subTest(action=action):
                with tempfile.TemporaryDirectory() as temp_dir:
                    ledger_path = Path(temp_dir) / "PROJECT_TASKS.json"
                    ledger = make_ledger(task)
                    ledger_path.write_text(json.dumps(ledger), encoding="utf-8")
                    output = io.StringIO()

                    with redirect_stdout(output):
                        exit_code = supervisor.main(
                            [action, "deploy", str(ledger_path)]
                        )

                    payload = json.loads(output.getvalue())
                    persisted = json.loads(ledger_path.read_text(encoding="utf-8"))
                    self.assertNotEqual(0, exit_code)
                    self.assertEqual("INVALID", payload["execution_state"])
                    self.assertEqual(ledger, persisted)

    def test_cli_external_lifecycle_rejects_invalid_receipts_without_mutation(self) -> None:
        cases = (
            (
                "--claim-external",
                "--authorization-json",
                make_task(
                    "deploy",
                    status="blocked_external",
                    execution="external",
                ),
                external_block_receipts(),
            ),
            (
                "--block-external",
                "--reason-json",
                make_task(
                    "deploy",
                    status="running",
                    execution="external",
                    verification=authorization_receipts(),
                ),
                authorization_receipts(),
            ),
        )
        for action, receipt_flag, task, invalid_receipts in cases:
            with self.subTest(action=action):
                with tempfile.TemporaryDirectory() as temp_dir:
                    ledger_path = Path(temp_dir) / "PROJECT_TASKS.json"
                    ledger = make_ledger(task)
                    ledger_path.write_text(json.dumps(ledger), encoding="utf-8")
                    output = io.StringIO()

                    with redirect_stdout(output):
                        exit_code = supervisor.main(
                            [
                                action,
                                "deploy",
                                receipt_flag,
                                json.dumps(invalid_receipts),
                                str(ledger_path),
                            ]
                        )

                    payload = json.loads(output.getvalue())
                    persisted = json.loads(ledger_path.read_text(encoding="utf-8"))
                    self.assertNotEqual(0, exit_code)
                    self.assertEqual("INVALID", payload["execution_state"])
                    self.assertEqual(ledger, persisted)

    def test_cycle_is_rejected(self) -> None:
        ledger = make_ledger(
            make_task("a", depends_on=["b"]),
            make_task("b", depends_on=["a"]),
        )

        with self.assertRaises(supervisor.LedgerValidationError) as caught:
            supervisor.analyze_ledger(ledger)

        self.assertTrue(
            any("dependency cycle detected" in error for error in caught.exception.errors)
        )

    def test_missing_dependency_is_rejected(self) -> None:
        ledger = make_ledger(make_task("a", depends_on=["missing"]))

        with self.assertRaises(supervisor.LedgerValidationError) as caught:
            supervisor.analyze_ledger(ledger)

        self.assertIn(
            "task 'a' depends on missing task 'missing'",
            caught.exception.errors,
        )

    def test_duplicate_id_invalid_state_and_empty_graph_are_rejected(self) -> None:
        cases = (
            make_ledger(make_task("same"), make_task("same")),
            make_ledger(make_task("bad", status="paused")),
            make_ledger(),
        )
        for ledger in cases:
            with self.subTest(ledger=ledger):
                with self.assertRaises(supervisor.LedgerValidationError):
                    supervisor.analyze_ledger(ledger)

    def test_non_string_status_and_execution_return_validation_errors(self) -> None:
        task = make_task("bad-types")
        task["status"] = []
        task["execution"] = {}

        with self.assertRaises(supervisor.LedgerValidationError) as caught:
            supervisor.analyze_ledger(make_ledger(task))

        self.assertEqual(2, len(caught.exception.errors))
        self.assertTrue(any("status must be one of" in error for error in caught.exception.errors))
        self.assertTrue(
            any("execution must be one of" in error for error in caught.exception.errors)
        )

    def test_long_acyclic_chain_does_not_depend_on_recursion_depth(self) -> None:
        tasks = [make_task("task-0", status="completed")]
        for index in range(1, 1200):
            tasks.append(make_task(f"task-{index}", depends_on=[f"task-{index - 1}"]))

        result = supervisor.analyze_ledger(make_ledger(*tasks))

        self.assertEqual("RUNNING", result["execution_state"])
        self.assertEqual("task-1", result["next_task_id"])

    def test_cli_defaults_to_project_tasks_and_outputs_json(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "PROJECT_TASKS.json").write_text(
                json.dumps(make_ledger(make_task("work"))),
                encoding="utf-8",
            )
            previous_cwd = Path.cwd()
            output = io.StringIO()
            try:
                os.chdir(root)
                with redirect_stdout(output):
                    exit_code = supervisor.main([])
            finally:
                os.chdir(previous_cwd)

        payload = json.loads(output.getvalue())
        self.assertEqual(0, exit_code)
        self.assertEqual("RUNNING", payload["execution_state"])
        self.assertEqual("work", payload["next_task_id"])

    def test_cli_validation_error_is_json_and_nonzero(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            ledger_path = Path(temp_dir) / "invalid.json"
            ledger_path.write_text(
                json.dumps(make_ledger(make_task("a", depends_on=["missing"]))),
                encoding="utf-8",
            )
            output = io.StringIO()
            with redirect_stdout(output):
                exit_code = supervisor.main([str(ledger_path)])

        payload = json.loads(output.getvalue())
        self.assertNotEqual(0, exit_code)
        self.assertEqual("INVALID", payload["execution_state"])
        self.assertTrue(payload["errors"])


if __name__ == "__main__":
    unittest.main()
