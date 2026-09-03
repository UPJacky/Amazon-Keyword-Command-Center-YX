import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from worker.pipeline.task_runner import run_task
from worker.rule_engine.engine import load_default_config

FIXTURE = Path(__file__).resolve().parents[2] / "data/fixtures/商品推广_搜索词_报告_LED演示.xlsx"


class ProviderPipelineTests(unittest.TestCase):
    def test_real_orchestrator_hook_runs_through_pipeline_and_reuses_cache(self):
        from worker.providers.cache import ProviderCache
        from worker.providers.orchestrator import CallBudget, ProviderBatchOrchestrator, ProviderRequest
        with tempfile.TemporaryDirectory() as directory:
            transport = Mock()
            transport.call.return_value = {"keyword": "led light", "search_volume": 100}
            budget = CallBudget(1)
            batch = ProviderBatchOrchestrator(provider="fake", provider_version="v1", normalizer_version="v1", cache_namespace="test-user", cache=ProviderCache(Path(directory) / "cache", 3600), normalize=lambda raw: raw, transport=transport, budget=budget, enabled=True)
            enricher = batch.as_enricher(lambda parsed, config: [ProviderRequest("fake_tool", {"keyword": "led light"})])
            for run in ("run-1", "run-2"):
                result = run_task(FIXTURE, directory, "task", run, provider_enricher=enricher)
                self.assertEqual("completed", result.status)
            self.assertEqual(1, transport.call.call_count)
            self.assertEqual(1, budget.used)
            usage = json.loads((Path(directory) / "task/run-2/provider-usage.json").read_text(encoding="utf-8"))
            self.assertEqual(0, usage["usage"]["actual_calls"])
            self.assertEqual(1, usage["usage"]["cache_hits"])

    def payload(self):
        return {"market_rows": [], "provider_snapshot_version": "snapshot-local-test", "usage": {"actual_calls": 0, "cache_hits": 1}}

    def test_explicit_enrichment_records_lineage_without_mutating_rules(self):
        config = load_default_config()
        before = json.dumps(config, sort_keys=True)
        def enrich(parsed, copied_config):
            copied_config.clear()
            parsed.clear()
            return self.payload()
        with tempfile.TemporaryDirectory() as directory:
            result = run_task(FIXTURE, directory, "task", "run", config=config, provider_enricher=enrich)
            self.assertEqual("completed", result.status)
            root = Path(directory) / "task/run"
            usage = json.loads((root / "provider-usage.json").read_text(encoding="utf-8"))
            report = json.loads((root / "master-table.json").read_text(encoding="utf-8"))
            self.assertEqual(report["provider_snapshot_version"], usage["provider_snapshot_version"])
            self.assertEqual(0, usage["usage"]["actual_calls"])
        self.assertEqual(before, json.dumps(config, sort_keys=True))

    def test_invalid_input_or_config_does_not_call_provider(self):
        for source, config in [(Path("missing-provider-input.xlsx"), None), (FIXTURE, {"acos": {"target": 2}})]:
            with self.subTest(source=source), tempfile.TemporaryDirectory() as directory:
                enrich = Mock()
                result = run_task(source, directory, "task", "run", config=config, provider_enricher=enrich)
                self.assertEqual("failed", result.status)
                enrich.assert_not_called()

    def test_failed_reconciliation_does_not_call_provider(self):
        parsed = {"input_file": "fake", "input_sha256": "hash", "parser_version": "test", "currency_code": "USD", "reconciliation": {"passed": False}}
        with tempfile.TemporaryDirectory() as directory, patch("worker.pipeline.task_runner.parse_report", return_value=parsed):
            enrich = Mock()
            result = run_task(FIXTURE, directory, "task", "run", provider_enricher=enrich)
            self.assertEqual("reconciliation", result.current_stage)
            enrich.assert_not_called()

    def test_conflicting_snapshot_does_not_call_provider(self):
        with tempfile.TemporaryDirectory() as directory:
            enrich = Mock()
            result = run_task(FIXTURE, directory, "task", "run", market_rows=[], provider_enricher=enrich)
            self.assertEqual("PROVIDER_ENRICHMENT_FAILED", result.failure_reason["code"])
            enrich.assert_not_called()

    def test_provider_failure_does_not_persist_exception_contents(self):
        with tempfile.TemporaryDirectory() as directory:
            marker = "DO-NOT-PERSIST-THIS-EXCEPTION"
            result = run_task(FIXTURE, directory, "task", "run", provider_enricher=Mock(side_effect=RuntimeError(marker)))
            self.assertEqual("provider", result.current_stage)
            self.assertNotIn(marker, (Path(directory) / "task/run/failure.json").read_text())
            self.assertFalse((Path(directory) / "task/run/master-table.json").exists())

    def test_invalid_enrichment_fails_closed(self):
        invalid = [None, {}, {**self.payload(), "market_rows": [{}], "usage": {"actual_calls": True}}, {**self.payload(), "usage": {"actual_calls": -1}}, {**self.payload(), "provider_snapshot_version": "../invalid"}, {**self.payload(), "market_rows": [{"rank": float("nan")}]}, {**self.payload(), "unexpected": "value"}]
        for value in invalid:
            with self.subTest(value=value), tempfile.TemporaryDirectory() as directory:
                result = run_task(FIXTURE, directory, "task", "run", provider_enricher=lambda *_: value)
                self.assertEqual("provider", result.current_stage)
                self.assertEqual("failed", result.status)


if __name__ == "__main__":
    unittest.main()
