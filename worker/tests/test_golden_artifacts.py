import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class GoldenArtifactContractTests(unittest.TestCase):
    def test_report_goldens_have_current_schema_and_matching_versions(self):
        for name in ("full-demo-report", "market-demo-report"):
            directory = ROOT / "data" / "golden" / name
            master = json.loads((directory / "master-table.json").read_text(encoding="utf-8"))
            actions = json.loads((directory / "action-results.json").read_text(encoding="utf-8"))
            meta = json.loads((directory / "report-meta.json").read_text(encoding="utf-8"))
            self.assertEqual(master["schema_version"], "report-0.2")
            self.assertEqual(actions["schema_version"], master["schema_version"])
            self.assertEqual(meta["schema_version"], master["schema_version"])
            self.assertIsInstance(master["missing_fields"], list)
            for artifact in (actions, meta):
                self.assertEqual(artifact["rule_version"], master["rule_version"])
                self.assertEqual(artifact["config_version"], master["config_version"])
                self.assertEqual(artifact["reconciliation_passed"], master["reconciliation"]["passed"])
                self.assertEqual(artifact["missing_fields"], master["missing_fields"])
            self.assertEqual(actions["input_file"], master["input_file"])
            self.assertEqual(actions["input_sha256"], master["input_sha256"])
            self.assertEqual(actions["currency_code"], master["currency_code"])
            self.assertEqual(actions["reconciliation_passed"], master["reconciliation"]["passed"])
            for field in ("input_file", "input_sha256", "currency_code", "rule_version", "config_version", "provider_snapshot_version"):
                self.assertEqual(meta[field], master[field])
            self.assertEqual(meta["reconciliation_passed"], actions["reconciliation_passed"])
            self.assertEqual(actions["rows"], master["rows"])

    def test_module_goldens_keep_unknown_rank_as_null_and_never_write_back(self):
        rank = json.loads((ROOT / "data" / "golden" / "market-demo-modules" / "rank-benchmark.json").read_text(encoding="utf-8"))
        negative = json.loads((ROOT / "data" / "golden" / "market-demo-modules" / "negative-keywords.json").read_text(encoding="utf-8"))
        self.assertEqual(rank["schema_version"], "module02-0.1")
        self.assertEqual(negative["schema_version"], "module03-0.1")
        self.assertFalse(negative["write_back"])
        for row in rank["rows"]:
            if row["my_organic_rank"] is None:
                self.assertIsNone(row["rank_gap"])


if __name__ == "__main__":
    unittest.main()
