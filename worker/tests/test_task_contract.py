import unittest

from worker.api.task_contract import FailureReason, create_task_contract, rerun_contract, transition


class TaskContractTests(unittest.TestCase):
    def test_legal_transitions(self):
        self.assertEqual(transition("pending", "processing"), "processing")
        self.assertEqual(transition("processing", "completed"), "completed")
        with self.assertRaises(ValueError):
            transition("completed", "processing")

    def test_contracts_preserve_run_lineage_and_failure_shape(self):
        task = create_task_contract(task_id="t1", created_by="u1", store_id="s1", input_file_path="u1/t1.xlsx", input_file_hash="abc")
        rerun = rerun_contract(task_id="t1", previous_run_id="r1", run_id="r2")
        self.assertEqual(task["status"], "pending")
        self.assertEqual(rerun["previous_run_id"], "r1")
        self.assertEqual(FailureReason("RECONCILIATION_FAILED", "stop", "reconciliation").to_dict()["retryable"], False)

    def test_contracts_reject_unsafe_or_empty_identifiers(self):
        with self.assertRaises(ValueError):
            create_task_contract(task_id="../escape", created_by="u1", store_id="s1", input_file_path="x.xlsx", input_file_hash="abc")
        with self.assertRaises(ValueError):
            rerun_contract(task_id="t1", previous_run_id="", run_id="r2")

    def test_rerun_requires_a_new_run_id(self):
        with self.assertRaises(ValueError):
            rerun_contract(task_id="t1", previous_run_id="r1", run_id="r1")


if __name__ == "__main__":
    unittest.main()
