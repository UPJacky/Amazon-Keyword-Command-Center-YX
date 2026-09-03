import tempfile
import unittest
from pathlib import Path
from threading import Event
from unittest.mock import patch

from worker.queue.file_queue import FileQueue
from worker.queue.runner import run_one
from worker.queue.supervisor import run_loop


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "data" / "fixtures" / "商品推广_搜索词_报告_LED演示.xlsx"


class QueueRunnerTests(unittest.TestCase):
    def test_run_one_claims_and_completes(self):
        with tempfile.TemporaryDirectory() as directory:
            queue_root = Path(directory) / "queue"
            storage_root = Path(directory) / "storage"
            FileQueue(queue_root).enqueue({"task_id": "task-1", "run_id": "run-1", "input_path": str(FIXTURE)})
            result = run_one(queue_root, storage_root)
            self.assertEqual(result["status"], "completed")
            self.assertTrue((queue_root / "completed" / "task-1__run-1.json").is_file())

    def test_supervisor_processes_multiple_tasks_and_waits_on_empty_queue(self):
        with tempfile.TemporaryDirectory() as directory:
            queue_root = Path(directory) / "queue"
            storage_root = Path(directory) / "storage"
            FileQueue(queue_root).enqueue({"task_id": "task-1", "run_id": "run-1", "input_path": str(FIXTURE)})
            FileQueue(queue_root).enqueue({"task_id": "task-2", "run_id": "run-2", "input_path": str(FIXTURE)})
            sleeps = []
            stats = run_loop(queue_root, storage_root, poll_interval=0.25, max_cycles=3, sleep_fn=sleeps.append)
            self.assertEqual(stats.processed, 2)
            self.assertEqual(stats.empty_cycles, 1)
            self.assertEqual(stats.errors, 0)
            self.assertEqual(sleeps, [0.25])

    def test_supervisor_stops_gracefully_before_polling(self):
        event = Event()
        event.set()
        stats = run_loop("queue", "storage", stop_event=event)
        self.assertTrue(stats.stopped)
        self.assertEqual(stats.cycles, 0)

    def test_supervisor_recovers_interrupted_tasks_before_polling(self):
        with tempfile.TemporaryDirectory() as directory:
            queue_root = Path(directory) / "queue"
            storage_root = Path(directory) / "storage"
            queue = FileQueue(queue_root)
            queue.enqueue({"task_id": "task-1", "run_id": "run-1", "input_path": str(FIXTURE)})
            queue.claim_next()
            stats = run_loop(queue_root, storage_root, max_cycles=1, run_fn=lambda *_: None, sleep_fn=lambda _: None)
            self.assertEqual(stats.recovered, 1)
            self.assertTrue((queue_root / "pending" / "task-1__run-1.json").is_file())

    def test_supervisor_uses_bounded_backoff_after_repeated_errors(self):
        sleeps = []

        def always_fails(*_):
            raise RuntimeError("temporary queue failure")

        stats = run_loop(
            "queue",
            "storage",
            poll_interval=0.5,
            max_backoff=1.0,
            max_cycles=3,
            run_fn=always_fails,
            sleep_fn=sleeps.append,
        )
        self.assertEqual(stats.errors, 3)
        self.assertEqual(stats.cycles, 3)
        self.assertEqual(sleeps, [0.5, 1.0, 1.0])

    def test_supervisor_never_sleeps_longer_than_backoff_cap_on_first_wait(self):
        sleeps = []

        def always_fails(*_):
            raise RuntimeError("temporary queue failure")

        stats = run_loop(
            "queue",
            "storage",
            poll_interval=5.0,
            max_backoff=0.0,
            max_cycles=2,
            run_fn=always_fails,
            sleep_fn=sleeps.append,
        )
        self.assertEqual(stats.errors, 2)
        self.assertEqual(sleeps, [0.0, 0.0])

    def test_supervisor_counts_completed_and_failed_results_separately(self):
        results = iter([
            {"status": "failed", "failure_reason": {"code": "INPUT_INVALID"}},
            {"status": "completed"},
        ])
        stats = run_loop(
            "queue",
            "storage",
            max_cycles=2,
            run_fn=lambda *_: next(results),
            sleep_fn=lambda _: None,
        )
        self.assertEqual(stats.processed, 2)
        self.assertEqual(stats.failed, 1)
        self.assertEqual(stats.errors, 0)

    def test_supervisor_emits_heartbeat_when_configured(self):
        heartbeats = []
        stats = run_loop(
            "queue",
            "storage",
            max_cycles=2,
            heartbeat_interval=0,
            heartbeat_fn=heartbeats.append,
            sleep_fn=lambda _: None,
        )
        self.assertEqual(stats.empty_cycles, 2)
        self.assertEqual(len(heartbeats), 2)
        self.assertEqual(heartbeats[-1].cycles, 2)

    def test_unexpected_task_error_is_archived_as_failed(self):
        with tempfile.TemporaryDirectory() as directory:
            queue_root = Path(directory) / "queue"
            storage_root = Path(directory) / "storage"
            FileQueue(queue_root).enqueue({"task_id": "task-1", "run_id": "run-1", "input_path": str(FIXTURE)})
            with patch("worker.queue.runner.run_task", side_effect=RuntimeError("simulated failure")):
                result = run_one(queue_root, storage_root)
            self.assertEqual(result["status"], "failed")
            self.assertEqual(result["failure_reason"]["code"], "UNEXPECTED_TASK_ERROR")
            self.assertTrue((queue_root / "failed" / "task-1__run-1.json").is_file())
            self.assertFalse((queue_root / "processing" / "task-1__run-1.json").exists())

    def test_result_conflict_does_not_wedge_continuous_worker(self):
        with tempfile.TemporaryDirectory() as directory:
            queue_root = Path(directory) / "queue"
            storage_root = Path(directory) / "storage"
            queue = FileQueue(queue_root)
            task = {"task_id": "task-1", "run_id": "run-1", "input_path": str(FIXTURE)}
            queue.enqueue(task)
            queue.claim_next()
            completed = queue_root / "completed" / "task-1__run-1.json"
            completed.write_text("existing", encoding="utf-8")
            stats = run_loop(queue_root, storage_root, max_cycles=2, sleep_fn=lambda _: None)
            self.assertEqual(stats.errors, 1)
            self.assertEqual(stats.empty_cycles, 1)
            self.assertFalse((queue_root / "processing" / "task-1__run-1.json").exists())
            self.assertTrue(list((queue_root / "failed").glob("task-1__run-1__result-conflict*.json")))

    def test_finish_rejects_symlinked_processing_item(self):
        with tempfile.TemporaryDirectory() as directory:
            queue = FileQueue(directory)
            outside = Path(directory) / "outside.json"
            outside.write_text('{"task_id":"task-1","run_id":"run-1","input_path":"demo.xlsx"}', encoding="utf-8")
            processing = Path(directory) / "processing" / "task-1__run-1.json"
            try:
                processing.symlink_to(outside)
            except (OSError, NotImplementedError):
                self.skipTest("symbolic links unavailable in this environment")
            with self.assertRaises(QueueError):
                queue.finish("task-1", "run-1", "completed", {"ok": True})

    def test_symlinked_pending_item_is_archived_without_reading_target(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "queue"
            queue = FileQueue(root)
            outside = Path(directory) / "outside.json"
            outside.write_text('{"task_id":"external","run_id":"run-1"}', encoding="utf-8")
            link = root / "pending" / "task-1__run-1.json"
            try:
                link.symlink_to(outside)
            except (OSError, NotImplementedError):
                self.skipTest("symbolic links unavailable in this environment")
            self.assertIsNone(queue.claim_next())
            self.assertTrue((root / "failed" / "task-1__run-1.json").is_file())
            self.assertTrue(outside.is_file())


if __name__ == "__main__":
    unittest.main()
