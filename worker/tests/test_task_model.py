import unittest

from worker.tasks.task_model import Run, Task, to_record


class TaskModelTests(unittest.TestCase):
    def test_rerun_has_new_run_id_and_preserves_previous_reference(self):
        task = Task(task_id="task-1", input_file_hash="abc")
        first = Run(task_id=task.task_id, rule_version="r1", config_version="c1", provider_snapshot_version="p1")
        second = Run(task_id=task.task_id, previous_run_id=first.run_id, rule_version="r1", config_version="c1", provider_snapshot_version="p1")
        self.assertNotEqual(first.run_id, second.run_id)
        self.assertEqual(second.previous_run_id, first.run_id)
        self.assertEqual(first.reproducibility_key("abc"), second.reproducibility_key("abc"))

    def test_record_is_json_friendly(self):
        record = to_record(Task(task_id="task-1", competitor_asins=("B1",), core_keywords=("led light",)))
        self.assertEqual(record["competitor_asins"], ["B1"])
        self.assertEqual(record["core_keywords"], ["led light"])


if __name__ == "__main__":
    unittest.main()

