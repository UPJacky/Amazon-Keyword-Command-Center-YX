import tempfile
import unittest
import json
from pathlib import Path

from worker.pipeline.task_runner import run_task


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "data" / "fixtures" / "商品推广_搜索词_报告_LED演示.xlsx"


class TaskRunnerTests(unittest.TestCase):
    def test_success_writes_task_run_artifacts(self):
        with tempfile.TemporaryDirectory() as directory:
            result = run_task(FIXTURE, directory, "task-1", "run-1")
            self.assertEqual(result.status, "completed")
            self.assertTrue((Path(directory) / "task-1" / "run-1" / "master-table.json").is_file())
            self.assertTrue((Path(directory) / "task-1" / "run-1" / "run-meta.json").is_file())
            root = Path(directory) / "task-1" / "run-1"
            self.assertTrue((root / "input-meta.json").is_file())
            self.assertTrue((root / "rules-snapshot.json").is_file())
            self.assertTrue((root / "rank-benchmark.json").is_file())
            self.assertTrue((root / "negative-keywords.json").is_file())
            self.assertTrue((root / "optimization-plan.json").is_file())
            self.assertEqual((root / "input-meta.json").read_text(encoding="utf-8").count("input_sha256"), 1)
            self.assertIn('"rule_version": "rule-v0.1"', (root / "rules-snapshot.json").read_text(encoding="utf-8"))

    def test_run_meta_matches_report_traceability_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            result = run_task(FIXTURE, directory, "task-1", "run-1", provider_snapshot_version="snapshot-v1")
            self.assertEqual(result.status, "completed")
            root = Path(directory) / "task-1" / "run-1"
            master = json.loads((root / "master-table.json").read_text(encoding="utf-8"))
            actions = json.loads((root / "action-results.json").read_text(encoding="utf-8"))
            meta = json.loads((root / "report-meta.json").read_text(encoding="utf-8"))
            run_meta = json.loads((root / "run-meta.json").read_text(encoding="utf-8"))
            shared = ("schema_version", "input_file", "input_sha256", "currency_code", "rule_version", "config_version", "provider_snapshot_version")
            for field in shared:
                self.assertEqual(run_meta[field], master[field])
                self.assertEqual(run_meta[field], actions[field])
                self.assertEqual(run_meta[field], meta[field])
            self.assertEqual(run_meta["missing_fields"], master["missing_fields"])
            self.assertEqual(run_meta["missing_fields"], actions["missing_fields"])
            self.assertEqual(run_meta["missing_fields"], meta["missing_fields"])
            self.assertEqual(run_meta["reconciliation_passed"], master["reconciliation"]["passed"])
            self.assertEqual(run_meta["reconciliation_passed"], actions["reconciliation_passed"])
            self.assertEqual(run_meta["reconciliation_passed"], meta["reconciliation_passed"])
            self.assertEqual(
                set(run_meta) - {"task_id", "run_id", "status", "current_stage"},
                (set(master) - {"reconciliation", "summary", "rows"}) | {"reconciliation_passed"},
            )

    def test_invalid_input_stops_before_report(self):
        with tempfile.TemporaryDirectory() as directory:
            result = run_task(Path(directory) / "missing.xlsx", directory, "task-1", "run-1")
            self.assertEqual(result.status, "failed")
            self.assertEqual(result.current_stage, "ingestion")
            self.assertFalse((Path(directory) / "task-1" / "run-1" / "master-table.json").exists())

    def test_symlink_input_is_rejected_as_structured_ingestion_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            link = Path(directory) / "input.csv"
            try:
                link.symlink_to(FIXTURE)
            except (OSError, NotImplementedError):
                self.skipTest("symbolic links unavailable in this environment")
            result = run_task(link, Path(directory) / "storage", "task-1", "run-1")
            self.assertEqual(result.status, "failed")
            self.assertEqual(result.current_stage, "ingestion")
            self.assertEqual(result.failure_reason["code"], "INPUT_INVALID")

    def test_duplicate_run_refuses_to_overwrite_existing_artifacts(self):
        with tempfile.TemporaryDirectory() as directory:
            first = run_task(FIXTURE, directory, "task-1", "run-1")
            report = Path(directory) / "task-1" / "run-1" / "master-table.json"
            original = report.read_text(encoding="utf-8")
            second = run_task(FIXTURE, directory, "task-1", "run-1")
            self.assertEqual(first.status, "completed")
            self.assertEqual(second.failure_reason["code"], "DUPLICATE_TASK_RUN")
            self.assertEqual(report.read_text(encoding="utf-8"), original)

    def test_invalid_config_stops_before_report(self):
        with tempfile.TemporaryDirectory() as directory:
            result = run_task(FIXTURE, directory, "task-1", "run-1", config={"acos": {"target": 2}})
            self.assertEqual(result.status, "failed")
            self.assertEqual(result.current_stage, "config")
            self.assertEqual(result.failure_reason["code"], "CONFIG_INVALID")
            self.assertFalse((Path(directory) / "task-1" / "run-1" / "master-table.json").exists())

    def test_competitor_profile_is_written_when_provided(self):
        with tempfile.TemporaryDirectory() as directory:
            profile = {
                "self_asin": "B000000001",
                "competitors": [{"asin": "B000000002"}, {"asin": "B000000003"}, {"asin": "B000000004"}],
                "core_keywords": ["led light"],
            }
            result = run_task(FIXTURE, directory, "task-1", "run-1", competitor_profile=profile)
            self.assertEqual(result.status, "completed")
            self.assertTrue((Path(directory) / "task-1" / "run-1" / "competitors.json").is_file())

    def test_invalid_competitor_profile_stops_before_formal_report(self):
        with tempfile.TemporaryDirectory() as directory:
            result = run_task(FIXTURE, directory, "task-1", "run-1", competitor_profile={"self_asin": "B000000001", "competitors": []})
            self.assertEqual(result.failure_reason["code"], "COMPETITOR_PROFILE_INVALID")
            self.assertFalse((Path(directory) / "task-1" / "run-1" / "master-table.json").exists())


if __name__ == "__main__":
    unittest.main()
