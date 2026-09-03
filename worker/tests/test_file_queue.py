import json
import tempfile
import unittest
from pathlib import Path

from worker.queue.file_queue import FileQueue, QueueError


class FileQueueTests(unittest.TestCase):
    def test_enqueue_claim_and_finish(self):
        with tempfile.TemporaryDirectory() as directory:
            queue = FileQueue(directory)
            queue.enqueue({"task_id": "task-1", "run_id": "run-1", "input_path": "demo.xlsx"})
            claimed = queue.claim_next()
            self.assertEqual(claimed["task_id"], "task-1")
            output = queue.finish("task-1", "run-1", "completed", {"ok": True})
            self.assertTrue(output.is_file())
            self.assertIsNone(queue.claim_next())

    def test_duplicate_and_invalid_ids_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            queue = FileQueue(directory)
            queue.enqueue({"task_id": "task-1", "run_id": "run-1", "input_path": "demo.xlsx"})
            with self.assertRaises(QueueError):
                queue.enqueue({"task_id": "task-1", "run_id": "run-1"})
            with self.assertRaises(QueueError):
                queue.enqueue({"task_id": "../escape", "run_id": "run-2"})

    def test_init_rejects_redirected_state_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "queue"
            root.mkdir()
            outside = Path(directory) / "outside"
            outside.mkdir()
            try:
                (root / "pending").symlink_to(outside, target_is_directory=True)
            except (OSError, NotImplementedError):
                self.skipTest("symbolic links unavailable")
            with self.assertRaises(QueueError):
                FileQueue(root)

    def test_operations_reject_root_redirected_after_initialization(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "queue"
            queue = FileQueue(root)
            outside = Path(directory) / "outside"
            outside.mkdir()
            backup = Path(directory) / "queue-backup"
            try:
                root.rename(backup)
                root.symlink_to(outside, target_is_directory=True)
            except (OSError, NotImplementedError):
                if root.is_symlink():
                    root.unlink()
                if backup.exists():
                    backup.rename(root)
                self.skipTest("symbolic links unavailable")
            try:
                with self.assertRaises(QueueError):
                    queue.claim_next()
            finally:
                root.unlink()
                backup.rename(root)

    def test_enqueue_rejects_invalid_payload_before_writing(self):
        with tempfile.TemporaryDirectory() as directory:
            queue = FileQueue(directory)
            with self.assertRaises(QueueError):
                queue.enqueue({"task_id": "task-1", "run_id": "run-1"})
            self.assertEqual(list((Path(directory) / "pending").glob("*")), [])

    def test_finish_does_not_overwrite_existing_result(self):
        with tempfile.TemporaryDirectory() as directory:
            queue = FileQueue(directory)
            task = {"task_id": "task-1", "run_id": "run-1", "input_path": "demo.xlsx"}
            queue.enqueue(task)
            queue.claim_next()
            destination = Path(directory) / "completed" / "task-1__run-1.json"
            destination.write_text("existing", encoding="utf-8")
            with self.assertRaises(QueueError):
                queue.finish("task-1", "run-1", "completed", {"ok": True})
            self.assertEqual(destination.read_text(encoding="utf-8"), "existing")
            self.assertTrue((Path(directory) / "processing" / "task-1__run-1.json").is_file())

    def test_recover_processing_moves_interrupted_task_back_to_pending(self):
        with tempfile.TemporaryDirectory() as directory:
            queue = FileQueue(directory)
            queue.enqueue({"task_id": "task-1", "run_id": "run-1", "input_path": "demo.xlsx"})
            queue.claim_next()
            self.assertEqual(queue.recover_processing(), 1)
            self.assertTrue((Path(directory) / "pending" / "task-1__run-1.json").is_file())
            self.assertFalse((Path(directory) / "processing" / "task-1__run-1.json").exists())

    def test_recover_processing_quarantines_collision_without_wedging(self):
        with tempfile.TemporaryDirectory() as directory:
            queue = FileQueue(directory)
            task = {"task_id": "task-1", "run_id": "run-1", "input_path": "demo.xlsx"}
            queue.enqueue(task)
            processing = Path(directory) / "processing" / "task-1__run-1.json"
            processing.write_text(json.dumps(task), encoding="utf-8")
            recovered = queue.recover_processing()
            self.assertEqual(recovered, 0)
            self.assertTrue((Path(directory) / "pending" / "task-1__run-1.json").is_file())
            self.assertFalse(processing.exists())
            conflict = list((Path(directory) / "failed").glob("task-1__run-1__result-conflict*.json"))
            self.assertEqual(len(conflict), 1)

    def test_invalid_json_is_archived_as_failed_and_does_not_block_queue(self):
        with tempfile.TemporaryDirectory() as directory:
            queue = FileQueue(directory)
            bad = Path(directory) / "pending" / "task-1__run-1.json"
            bad.write_bytes(b"not-json")
            queue.enqueue({"task_id": "task-2", "run_id": "run-2", "input_path": "demo.xlsx"})
            claimed = queue.claim_next()
            self.assertEqual(claimed["task_id"], "task-2")
            failed = Path(directory) / "failed" / "task-1__run-1.json"
            self.assertTrue(failed.is_file())
            self.assertIn("INVALID_QUEUE_PAYLOAD", failed.read_text(encoding="utf-8"))

    def test_invalid_json_object_is_archived_and_does_not_wedge_processing(self):
        with tempfile.TemporaryDirectory() as directory:
            queue = FileQueue(directory)
            bad = Path(directory) / "pending" / "task-1__run-1.json"
            bad.write_text('{"task_id":"task-1","run_id":"run-1"}', encoding="utf-8")
            queue.enqueue({"task_id": "z-task", "run_id": "run-2", "input_path": "demo.xlsx"})
            claimed = queue.claim_next()
            self.assertEqual(claimed["task_id"], "z-task")
            failed = Path(directory) / "failed" / "task-1__run-1.json"
            self.assertTrue(failed.is_file())
            self.assertIn("requires input_path", failed.read_text(encoding="utf-8"))

    def test_invalid_queue_archive_does_not_overwrite_existing_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            queue = FileQueue(directory)
            failed = Path(directory) / "failed" / "task-1__run-1.json"
            failed.write_text("historical", encoding="utf-8")
            bad = Path(directory) / "pending" / "task-1__run-1.json"
            bad.write_text('{"task_id":"task-1","run_id":"run-1"}', encoding="utf-8")
            self.assertIsNone(queue.claim_next())
            self.assertEqual(failed.read_text(encoding="utf-8"), "historical")
            self.assertTrue((Path(directory) / "failed" / "task-1__run-1__invalid-1.json").is_file())

    def test_input_file_path_contract_is_accepted(self):
        with tempfile.TemporaryDirectory() as directory:
            queue = FileQueue(directory)
            queue.enqueue({"task_id": "task-1", "run_id": "run-1", "input_file_path": "demo.xlsx"})
            self.assertEqual(queue.claim_next()["input_file_path"], "demo.xlsx")

    def test_filename_mismatch_is_archived_and_does_not_wedge_processing(self):
        with tempfile.TemporaryDirectory() as directory:
            queue = FileQueue(directory)
            bad = Path(directory) / "pending" / "wrong-name.json"
            bad.write_text('{"task_id":"task-1","run_id":"run-1","input_path":"demo.xlsx"}', encoding="utf-8")
            queue.enqueue({"task_id": "z-task", "run_id": "run-2", "input_path": "demo.xlsx"})
            claimed = queue.claim_next()
            self.assertEqual(claimed["task_id"], "z-task")
            failed = Path(directory) / "failed" / "wrong-name.json"
            self.assertTrue(failed.is_file())
            self.assertIn("filename does not match", failed.read_text(encoding="utf-8"))

    def test_same_run_cannot_be_reenqueued_after_completion(self):
        with tempfile.TemporaryDirectory() as directory:
            queue = FileQueue(directory)
            task = {"task_id": "task-1", "run_id": "run-1", "input_path": "demo.xlsx"}
            queue.enqueue(task)
            queue.claim_next()
            queue.finish("task-1", "run-1", "completed", {"ok": True})
            with self.assertRaises(QueueError):
                queue.enqueue(task)

    def test_finish_rejects_unsafe_ids_without_touching_outside_queue(self):
        with tempfile.TemporaryDirectory() as directory:
            queue = FileQueue(directory)
            with self.assertRaises(QueueError):
                queue.finish("../escape", "run-1", "completed", {})
            self.assertFalse((Path(directory).parent / "escape__run-1.json").exists())

    def test_result_conflict_is_quarantined_without_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            queue = FileQueue(directory)
            task = {"task_id": "task-1", "run_id": "run-1", "input_path": "demo.xlsx"}
            queue.enqueue(task)
            queue.claim_next()
            completed = Path(directory) / "completed" / "task-1__run-1.json"
            completed.write_text("existing", encoding="utf-8")
            conflict = queue.archive_processing_conflict("task-1", "run-1", "already exists")
            self.assertTrue(conflict.is_file())
            self.assertEqual(completed.read_text(encoding="utf-8"), "existing")
            self.assertFalse((Path(directory) / "processing" / "task-1__run-1.json").exists())

    def test_invalid_archive_does_not_follow_dangling_failure_link(self):
        with tempfile.TemporaryDirectory() as directory:
            queue = FileQueue(directory)
            failed = Path(directory) / "failed" / "task-1__run-1.json"
            try:
                failed.symlink_to(Path(directory) / "missing-target.json")
            except (OSError, NotImplementedError):
                self.skipTest("symbolic links unavailable")
            bad = Path(directory) / "pending" / "task-1__run-1.json"
            bad.write_text('{"task_id":"task-1","run_id":"run-1"}', encoding="utf-8")
            self.assertIsNone(queue.claim_next())
            self.assertTrue(failed.is_symlink())
            self.assertTrue((Path(directory) / "failed" / "task-1__run-1__invalid-1.json").is_file())

    def test_recovery_quarantines_processing_symlink_without_reading_target(self):
        with tempfile.TemporaryDirectory() as directory:
            queue = FileQueue(directory)
            outside = Path(directory) / "outside.json"
            outside.write_text('{"task_id":"evil","run_id":"run-1"}', encoding="utf-8")
            link = Path(directory) / "processing" / "task-1__run-1.json"
            try:
                link.symlink_to(outside)
            except (OSError, NotImplementedError):
                self.skipTest("symbolic links unavailable")
            self.assertEqual(queue.recover_processing(), 0)
            self.assertFalse(link.is_symlink())
            self.assertTrue((Path(directory) / "failed" / "task-1__run-1.json").is_file())

    def test_claim_does_not_overwrite_existing_processing_record(self):
        with tempfile.TemporaryDirectory() as directory:
            queue = FileQueue(directory)
            pending = Path(directory) / "pending" / "task-1__run-1.json"
            processing = Path(directory) / "processing" / "task-1__run-1.json"
            task = {"task_id": "task-1", "run_id": "run-1", "input_path": "demo.xlsx"}
            pending.write_text(json.dumps(task), encoding="utf-8")
            processing.write_text("historical-processing", encoding="utf-8")
            self.assertIsNone(queue.claim_next())
            self.assertEqual(processing.read_text(encoding="utf-8"), "historical-processing")
            self.assertTrue((Path(directory) / "failed" / "task-1__run-1.json").is_file())

    def test_recovery_collision_after_initial_check_is_quarantined(self):
        with tempfile.TemporaryDirectory() as directory:
            queue = FileQueue(directory)
            task = {"task_id": "task-1", "run_id": "run-1", "input_path": "demo.xlsx"}
            queue.enqueue(task)
            processing = Path(directory) / "processing" / "task-1__run-1.json"
            processing.write_text(json.dumps(task), encoding="utf-8")
            pending = Path(directory) / "pending" / "task-1__run-1.json"

            original_move = queue._move_without_overwrite
            def create_collision(source, target):
                if target == pending and not pending.exists():
                    pending.write_text(json.dumps(task), encoding="utf-8")
                return original_move(source, target)

            queue._move_without_overwrite = create_collision
            self.assertEqual(queue.recover_processing(), 0)
            self.assertFalse(processing.exists())
            self.assertTrue(list((Path(directory) / "failed").glob("*result-conflict*.json")))


if __name__ == "__main__":
    unittest.main()
