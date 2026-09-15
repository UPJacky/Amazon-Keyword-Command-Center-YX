import unittest
import hashlib

from worker.api.task_contract import FailureReason, create_task_contract, rerun_contract, transition


class TaskContractTests(unittest.TestCase):
    def valid_task(self, **overrides):
        values = {
            "task_id": "t1", "created_by": "u1", "store_id": "s1",
            "self_asin": "B012345678", "marketplace": "US",
            "product_stage": "stable", "input_file_path": "s1/u1/t1/input.xlsx",
            "input_file_hash": hashlib.sha256(b"input").hexdigest(), "input_size": 5,
        }
        values.update(overrides)
        return values

    def test_legal_transitions(self):
        self.assertEqual(transition("pending", "processing"), "processing")
        self.assertEqual(transition("processing", "completed"), "completed")
        with self.assertRaises(ValueError):
            transition("completed", "processing")

    def test_contracts_preserve_run_lineage_and_failure_shape(self):
        task = create_task_contract(**self.valid_task())
        rerun = rerun_contract(task_id="t1", previous_run_id="r1", run_id="r2")
        self.assertEqual(task["status"], "pending")
        self.assertEqual(rerun["previous_run_id"], "r1")
        self.assertEqual(FailureReason("RECONCILIATION_FAILED", "stop", "reconciliation").to_dict()["retryable"], False)

    def test_contracts_reject_unsafe_or_empty_identifiers(self):
        with self.assertRaises(ValueError):
            create_task_contract(**self.valid_task(task_id="../escape"))
        with self.assertRaises(ValueError):
            rerun_contract(task_id="t1", previous_run_id="", run_id="r2")

    def test_rerun_requires_a_new_run_id(self):
        with self.assertRaises(ValueError):
            rerun_contract(task_id="t1", previous_run_id="r1", run_id="r1")

    def test_create_contract_rejects_unbound_input_metadata(self):
        cases = (
            {"self_asin": "A012345678"}, {"self_asin": "B01234567"},
            {"marketplace": "us"}, {"product_stage": "unknown"},
            {"input_file_path": "../input.xlsx"},
            {"input_file_path": "s1/u1/t1/report.xlsx"},
            {"input_file_hash": "abc"}, {"input_file_hash": "g" * 64},
            {"input_size": 0}, {"input_size": 10 * 1024 * 1024 + 1},
            {"input_size": True},
        )
        for override in cases:
            with self.subTest(override=override):
                with self.assertRaises(ValueError):
                    create_task_contract(**self.valid_task(**override))


if __name__ == "__main__":
    unittest.main()
