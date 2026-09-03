import tempfile
import unittest
import json
from pathlib import Path

from worker.report.generate_report import build_report, report_missing_fields, shared_traceability


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "data" / "fixtures" / "商品推广_搜索词_报告_LED演示.xlsx"


class ReportGenerationTests(unittest.TestCase):
    def test_shared_traceability_is_complete_and_derived_from_master(self):
        with tempfile.TemporaryDirectory() as directory:
            report = build_report(FIXTURE, Path(directory) / "one", provider_snapshot_version="snapshot-v1")
            expected = shared_traceability(report)
            meta = json.loads((Path(directory) / "one" / "report-meta.json").read_text(encoding="utf-8"))
            actions = json.loads((Path(directory) / "one" / "action-results.json").read_text(encoding="utf-8"))
            self.assertEqual(meta, expected)
            self.assertEqual({key: actions[key] for key in expected}, expected)
            self.assertEqual(report["missing_fields"], report_missing_fields(report))

    def test_report_meta_summarizes_row_missing_fields_without_changing_rows(self):
        with tempfile.TemporaryDirectory() as directory:
            report = build_report(FIXTURE, Path(directory) / "one")
            meta = json.loads((Path(directory) / "one" / "report-meta.json").read_text(encoding="utf-8"))
            self.assertEqual(meta["missing_fields"], report_missing_fields(report))
            self.assertEqual(meta["missing_fields"], sorted({field for row in report["rows"] for field in row["missing_fields"]}))

    def test_report_contains_versions_counts_and_stable_rows(self):
        with tempfile.TemporaryDirectory() as directory:
            first = build_report(FIXTURE, Path(directory) / "one")
            second = build_report(FIXTURE, Path(directory) / "two")
            self.assertEqual(first["summary"]["keyword_count"], 91)
            self.assertEqual(first["reconciliation"]["passed"], True)
            self.assertEqual(first["rule_version"], "rule-v0.1")
            self.assertEqual(first["schema_version"], "report-0.2")
            self.assertEqual(first["config_version"], "stable-v1-template")
            self.assertIsNone(first["provider_snapshot_version"])
            self.assertEqual(first["rows"], second["rows"])
            self.assertTrue((Path(directory) / "one" / "master-table.json").is_file())
            self.assertTrue((Path(directory) / "one" / "action-results.json").is_file())
            action_results = json.loads((Path(directory) / "one" / "action-results.json").read_text(encoding="utf-8"))
            self.assertEqual(action_results["schema_version"], "report-0.2")
            self.assertEqual(action_results["input_file"], first["input_file"])
            self.assertEqual(action_results["input_sha256"], first["input_sha256"])
            self.assertEqual(action_results["currency_code"], first["currency_code"])
            self.assertTrue(action_results["reconciliation_passed"])
            report_meta = json.loads((Path(directory) / "one" / "report-meta.json").read_text(encoding="utf-8"))
            for field in ("schema_version", "input_file", "input_sha256", "currency_code", "rule_version", "config_version", "provider_snapshot_version"):
                self.assertEqual(report_meta[field], action_results[field])
            self.assertEqual(report_meta["reconciliation_passed"], action_results["reconciliation_passed"])

    def test_market_snapshot_changes_only_rule_context(self):
        snapshot = json.loads((ROOT / "data" / "golden" / "provider-snapshot-demo.json").read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as directory:
            report = build_report(FIXTURE, directory, market_rows=snapshot["records"])
            led = next(row for row in report["rows"] if row["keyword"] == "led light")
            room = next(row for row in report["rows"] if row["keyword"] == "room accessories")
            self.assertEqual(led["action_group"], "defend_rank")
            self.assertEqual(room["action_group"], "optimize_bid")
            self.assertEqual(led["clicks"], 131)

    def test_provider_nulls_flow_to_row_and_report_missing_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            report = build_report(
                FIXTURE,
                directory,
                market_rows=[{"keyword": "led light", "organic_rank": None, "suggested_bid": None}],
            )
            row = next(item for item in report["rows"] if item["keyword"] == "led light")
            self.assertEqual(row["missing_fields"], ["organic_rank", "suggested_bid"])
            self.assertEqual(report["missing_fields"], ["organic_rank", "suggested_bid"])
            meta = json.loads((Path(directory) / "report-meta.json").read_text(encoding="utf-8"))
            self.assertEqual(meta["missing_fields"], report["missing_fields"])

    def test_missing_field_projection_ignores_noncanonical_fixture_values(self):
        report = {"rows": [{"missing_fields": (" spend ", " ")}, {"missing_fields": "orders"}, {"missing_fields": 7}]}
        self.assertEqual(report_missing_fields(report), ["orders", "spend"])

    def test_traceability_does_not_coerce_string_reconciliation_to_true(self):
        trace = shared_traceability({"reconciliation": {"passed": "false"}, "rows": []})
        self.assertFalse(trace["reconciliation_passed"])
        self.assertFalse(shared_traceability({"reconciliation": {"passed": 1}, "rows": []})["reconciliation_passed"])

    def test_shared_missing_field_projection_skips_malformed_rows(self):
        report = {"rows": [None, {"missing_fields": [" z ", "z", " ", 7]}, {"missing_fields": " a "}]}
        self.assertEqual(report_missing_fields(report), ["a", "z"])

    def test_provider_snapshot_version_is_written_to_report_artifacts(self):
        with tempfile.TemporaryDirectory() as directory:
            report = build_report(FIXTURE, directory, provider_snapshot_version="snapshot-v1")
            self.assertEqual(report["provider_snapshot_version"], "snapshot-v1")
            meta = json.loads((Path(directory) / "report-meta.json").read_text(encoding="utf-8"))
            self.assertEqual(meta["provider_snapshot_version"], "snapshot-v1")

    def test_report_artifacts_are_immutable(self):
        with tempfile.TemporaryDirectory() as directory:
            build_report(FIXTURE, directory)
            with self.assertRaises(ValueError):
                build_report(FIXTURE, directory)

    def test_report_row_order_is_independent_of_market_snapshot_order(self):
        snapshot = json.loads((ROOT / "data" / "golden" / "provider-snapshot-demo.json").read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as directory:
            first = build_report(FIXTURE, Path(directory) / "one", market_rows=snapshot["records"])
            second = build_report(FIXTURE, Path(directory) / "two", market_rows=list(reversed(snapshot["records"])))
            self.assertEqual(first["rows"], second["rows"])


if __name__ == "__main__":
    unittest.main()
