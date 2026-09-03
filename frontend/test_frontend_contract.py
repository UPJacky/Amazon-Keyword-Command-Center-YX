import unittest
import json
from pathlib import Path

from contract_check import check


class FrontendContractTests(unittest.TestCase):
    def test_static_contract(self):
        self.assertEqual(check(), [])

    def test_report_02_artifact_has_traceable_rows_and_missing_value_semantics(self):
        artifact = Path(__file__).resolve().parent.parent / "data" / "golden" / "market-demo-report" / "master-table.json"
        report = json.loads(artifact.read_text(encoding="utf-8"))
        self.assertEqual(report["schema_version"], "report-0.2")
        self.assertRegex(report["currency_code"], r"^[A-Z]{3}$")
        self.assertTrue(report["input_sha256"])
        self.assertTrue(report["provider_snapshot_version"])
        self.assertTrue(report["reconciliation"]["passed"])
        self.assertTrue(report["rows"])
        for row in report["rows"]:
            self.assertIn("action_group", row)
            self.assertIn("ui_conclusion", row)
            self.assertIn("missing_fields", row)

    def test_report_contract_covers_all_action_mapping_filters(self):
        report_html = (Path(__file__).resolve().parent / "report.html").read_text(encoding="utf-8")
        for action_filter in ("all", "add", "defend", "keep", "cautious", "optimize", "stop_loss", "data_missing"):
            self.assertIn(f'data-action-filter="{action_filter}"', report_html)

    def test_task_meta_traceability_matches_report_artifact(self):
        root = Path(__file__).resolve().parent.parent
        report = json.loads((root / "data" / "golden" / "market-demo-report" / "master-table.json").read_text(encoding="utf-8"))
        actions = json.loads((root / "data" / "golden" / "market-demo-report" / "action-results.json").read_text(encoding="utf-8"))
        meta = json.loads((root / "data" / "golden" / "market-demo-report" / "report-meta.json").read_text(encoding="utf-8"))
        for field in ("schema_version", "input_file", "input_sha256", "currency_code", "rule_version", "config_version", "provider_snapshot_version", "missing_fields"):
            self.assertEqual(actions[field], report[field])
            self.assertEqual(meta[field], report[field])
        expected_reconciliation = report["reconciliation"].get("passed") is True
        self.assertIs(actions["reconciliation_passed"], expected_reconciliation)
        self.assertIs(meta["reconciliation_passed"], expected_reconciliation)
        self.assertIsInstance(report["missing_fields"], list)
        self.assertEqual(meta["missing_fields"], report["missing_fields"])
        self.assertEqual(actions["rows"], report["rows"])

    def test_task_and_report_pages_use_shared_traceability_contract(self):
        tasks_script = (Path(__file__).resolve().parent / "tasks.js").read_text(encoding="utf-8")
        report_script = (Path(__file__).resolve().parent / "report.js").read_text(encoding="utf-8")
        for marker in ("schema_version", "input_file", "input_sha256", "currency_code", "rule_version", "config_version", "provider_snapshot_version", "reconciliation_passed", "missing_fields"):
            self.assertIn(marker, tasks_script)
        for marker in ("schema_version", "input_file", "input_sha256", "currency_code", "provider_snapshot_version", "reconciliation", "missing_fields"):
            self.assertIn(marker, report_script)
        report_html = (Path(__file__).resolve().parent / "report.html").read_text(encoding="utf-8")
        self.assertIn('id="report-input-file"', report_html)
        self.assertIn('id="report-missing-fields"', report_html)
        self.assertIn("Array.isArray(value)", report_script)
        self.assertIn("new Set", report_script)
        self.assertIn("new Set", tasks_script)
        self.assertIn("passed === true", report_script)
        self.assertIn("reconciliation_passed === true", tasks_script)


if __name__ == "__main__":
    unittest.main()
