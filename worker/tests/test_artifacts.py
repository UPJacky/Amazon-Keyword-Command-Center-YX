import tempfile
import unittest
from pathlib import Path

from worker.storage.artifacts import ArtifactError, artifact_path, read_json, write_json


class ArtifactTests(unittest.TestCase):
    def test_allowlisted_artifact_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            path = write_json(directory, "task-1", "run-1", "report-meta.json", {"passed": True})
            self.assertEqual(path, Path(directory).resolve() / "task-1" / "run-1" / "report-meta.json")
            self.assertEqual(read_json(directory, "task-1", "run-1", "report-meta.json"), {"passed": True})

    def test_run_meta_is_an_allowlisted_traceability_artifact(self):
        with tempfile.TemporaryDirectory() as directory:
            path = write_json(directory, "task-1", "run-1", "run-meta.json", {"status": "completed"})
            self.assertEqual(path.name, "run-meta.json")
            self.assertEqual(read_json(directory, "task-1", "run-1", "run-meta.json"), {"status": "completed"})

    def test_rejects_traversal_and_unknown_artifact(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ArtifactError):
                artifact_path(directory, "../escape", "run-1", "report-meta.json")
            with self.assertRaises(ArtifactError):
                artifact_path(directory, "task-1", "run-1", "secret.txt")

    def test_write_does_not_overwrite_historical_artifact(self):
        with tempfile.TemporaryDirectory() as directory:
            write_json(directory, "task-1", "run-1", "report-meta.json", {"version": 1})
            with self.assertRaises(ArtifactError):
                write_json(directory, "task-1", "run-1", "report-meta.json", {"version": 2})
            self.assertEqual(read_json(directory, "task-1", "run-1", "report-meta.json"), {"version": 1})

    def test_write_rejects_redirected_run_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            outside = Path(directory) / "outside"
            outside.mkdir()
            run = Path(directory) / "task-1" / "run-1"
            run.parent.mkdir()
            try:
                run.symlink_to(outside, target_is_directory=True)
            except (OSError, NotImplementedError):
                self.skipTest("symbolic links unavailable")
            with self.assertRaises(ArtifactError):
                write_json(directory, "task-1", "run-1", "report-meta.json", {"secret": True})


    def test_read_rejects_symlinked_artifact(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "outside.json"
            target.write_text('{"secret": true}', encoding="utf-8")
            run = Path(directory) / "task-1" / "run-1"
            run.mkdir(parents=True)
            link = run / "report-meta.json"
            try:
                link.symlink_to(target)
            except (OSError, NotImplementedError):
                self.skipTest("symbolic links unavailable")
            with self.assertRaises(ArtifactError):
                read_json(directory, "task-1", "run-1", "report-meta.json")

    def test_rejects_symlinked_task_or_run_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            outside = Path(directory) / "outside"
            outside.mkdir()
            task_link = Path(directory) / "task-1"
            try:
                task_link.symlink_to(outside, target_is_directory=True)
            except (OSError, NotImplementedError):
                self.skipTest("symbolic links unavailable")
            with self.assertRaises(ArtifactError):
                artifact_path(directory, "task-1", "run-1", "report-meta.json")


if __name__ == "__main__":
    unittest.main()
