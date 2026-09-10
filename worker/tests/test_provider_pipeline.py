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
            report = json.loads(Path(result.report_path).read_text(encoding="utf-8"))
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
            self.assertFalse(list((Path(directory) / "task/run").glob("report-*.json")))

    def test_invalid_enrichment_fails_closed(self):
        invalid = [None, {}, {**self.payload(), "market_rows": [{}], "usage": {"actual_calls": True}}, {**self.payload(), "usage": {"actual_calls": -1}}, {**self.payload(), "provider_snapshot_version": "../invalid"}, {**self.payload(), "market_rows": [{"rank": float("nan")}]}, {**self.payload(), "unexpected": "value"}]
        for value in invalid:
            with self.subTest(value=value), tempfile.TemporaryDirectory() as directory:
                result = run_task(FIXTURE, directory, "task", "run", provider_enricher=lambda *_: value)
                self.assertEqual("provider", result.current_stage)
                self.assertEqual("failed", result.status)

    def test_visual_provider_evidence_is_projected_into_listing_artifact(self):
        evidence = {
            "expected_element_ids": ["hero_value_prop"],
            "evidence_version": "visual-v1",
            "observations": [{
                "image_id": "self-image-1", "element_id": "hero_value_prop",
                "evidence_region": "center", "visible_objects": ["product"],
                "visible_text": [], "answer_mode": "direct_visual",
                "prominence": "dominant", "legibility": "clear",
                "confidence": "high", "source_refs": ["self-image-1"],
            }],
        }
        def enrich(_parsed, _config):
            return {**self.payload(), "visual_evidence": evidence}
        profile = {"self_asin": "B012345678", "competitors": [],
                   "self_product": {"image_urls": ["https://img.example/self.jpg"]}}
        with tempfile.TemporaryDirectory() as directory:
            result = run_task(FIXTURE, directory, "task", "run", provider_enricher=enrich,
                              competitor_profile=profile, my_asin="B012345678")
            self.assertEqual("completed", result.status)
            listing = json.loads((Path(directory) / "task/run/listing-diagnostics.json").read_text(encoding="utf-8"))
            self.assertEqual("partial", listing["module_status"]["status"])
            self.assertEqual("hero_value_prop", listing["self_images"]["images"][0]["observations"][0]["element_id"])

    def test_share_board_is_persisted_without_swapping_denominators(self):
        def enrich(_parsed, _config):
            return {
                **self.payload(),
                "market_rows": [{
                    "keyword": "led light", "asin": "B012345678",
                    "keyword_market_share": 0.2,
                    "asin_keyword_dependency": 0.05,
                    "traffic_acquisition_rate": 0.7,
                }],
            }
        with tempfile.TemporaryDirectory() as directory:
            result = run_task(FIXTURE, directory, "task", "run", provider_enricher=enrich)
            self.assertEqual("completed", result.status)
            rank = json.loads((Path(directory) / "task/run/rank-benchmark.json").read_text(encoding="utf-8"))
            row = next(item for item in rank["share_board"] if item["keyword"] == "led light")
            self.assertEqual(20.0, row["keyword_market_share"]["display_percent"])
            self.assertEqual(5.0, row["asin_keyword_dependency"]["display_percent"])
            self.assertEqual(70.0, row["traffic_acquisition_rate"]["display_percent"])
            self.assertEqual("partial", rank["share_module_status"]["status"])

    def test_invalid_share_ratio_is_retained_and_not_clipped(self):
        def enrich(_parsed, _config):
            return {**self.payload(), "market_rows": [{"keyword": "led light", "keyword_market_share": 1.338}]}
        with tempfile.TemporaryDirectory() as directory:
            result = run_task(FIXTURE, directory, "task", "run", provider_enricher=enrich)
            self.assertEqual("completed", result.status)
            rank = json.loads((Path(directory) / "task/run/rank-benchmark.json").read_text(encoding="utf-8"))
            row = next(item for item in rank["share_board"] if item["keyword"] == "led light")
            self.assertEqual("invalid_value", row["keyword_market_share"]["status"])
            self.assertEqual(1.338, row["keyword_market_share"]["raw_value"])
            self.assertIsNone(row["keyword_market_share"]["value"])

    def test_invalid_visual_provider_evidence_fails_closed(self):
        invalid = {**self.payload(), "visual_evidence": {"expected_element_ids": [], "observations": []}}
        with tempfile.TemporaryDirectory() as directory:
            result = run_task(FIXTURE, directory, "task", "run", provider_enricher=lambda *_: invalid)
            self.assertEqual("failed", result.status)
            self.assertEqual("provider", result.current_stage)

    def test_category_features_are_persisted_as_a_separate_auditable_artifact(self):
        category = {
            "schema_version": "category-features-0.1",
            "primary_core_keyword": "led lights",
            "marketplace": "US",
            "features": [{"feature_id": "f1", "name": "调光", "product_count_share": 64.2,
                           "product_count_share_ratio": 0.642, "monthly_sales_share": 28.47,
                           "monthly_sales_share_ratio": 0.2847, "ratio": 0.642, "source_index": 0}],
            "feature_count": 1, "empty_name_count": 0, "invalid_rows": [],
            "source": "sorftime:similar_product_feature",
        }
        def enrich(_parsed, _config):
            return {**self.payload(), "category_features": category}
        with tempfile.TemporaryDirectory() as directory:
            result = run_task(FIXTURE, directory, "task", "run", provider_enricher=enrich)
            self.assertEqual("completed", result.status)
            artifact = json.loads((Path(directory) / "task/run/category-features.json").read_text(encoding="utf-8"))
            self.assertEqual("ready", artifact["module_status"]["status"])
            self.assertEqual("led lights", artifact["primary_core_keyword"])

    def test_invalid_category_features_fail_closed(self):
        invalid = {**self.payload(), "category_features": {"features": []}}
        with tempfile.TemporaryDirectory() as directory:
            result = run_task(FIXTURE, directory, "task", "run", provider_enricher=lambda *_: invalid)
            self.assertEqual("provider", result.current_stage)
            self.assertEqual("failed", result.status)

    def test_competitor_comparison_and_brief_are_persisted_with_explicit_image_refs(self):
        evidence = {
            "expected_element_ids": ["hero_value_prop"], "evidence_version": "visual-v1",
            "observations": [
                {"image_id": "self-image-1", "element_id": "hero_value_prop", "evidence_region": "center", "visible_objects": ["product"], "visible_text": [], "answer_mode": "direct_visual", "prominence": "dominant", "legibility": "clear", "confidence": "high", "source_refs": ["self-image-1"]},
                {"image_id": "B000000002-image-1", "element_id": "hero_value_prop", "evidence_region": "center", "visible_objects": ["product"], "visible_text": [], "answer_mode": "direct_visual", "prominence": "dominant", "legibility": "clear", "confidence": "high", "source_refs": ["B000000002-image-1"]},
            ],
        }
        evaluations = {item: {"status": "pass", "evidence": [item]} for item in ("hero_value_prop", "mobile_readability", "benefit_proof", "competitor_difference")}
        profile = {"self_asin": "B000000001", "competitors": [{"asin": "B000000002", "image_urls": ["https://cdn.example.com/comp.jpg"]}], "self_product": {"image_urls": ["https://cdn.example.com/self.jpg"]}}
        def enrich(_parsed, _config):
            return {**self.payload(), "visual_evidence": evidence, "checklist_evaluations": evaluations,
                    "competitor_comparisons": [{"competitor_asin": "B000000002", "element_id": "hero_value_prop", "status": "弱", "target_self_image_id": "self-image-1", "reference_competitor_image_id": "B000000002-image-1", "evidence": ["B000000002-image-1"], "specific_change": "强化层级"}],
                    "image_briefs": [{"self_image_id": "self-image-1", "label": "主图", "existing_expression": "产品主体", "references": [{"competitor_asin": "B000000002", "image_id": "B000000002-image-1"}], "truth_constraints": ["只写已确认功能"]}]}
        with tempfile.TemporaryDirectory() as directory:
            result = run_task(FIXTURE, directory, "task", "run", provider_enricher=enrich, competitor_profile=profile)
            self.assertEqual("completed", result.status)
            listing = json.loads((Path(directory) / "task/run/listing-diagnostics.json").read_text(encoding="utf-8"))
            self.assertEqual("ready", listing["visual_brief"]["module_status"]["status"])
            self.assertEqual("B000000002-image-1", listing["visual_brief"]["briefs"][0]["references"][0]["image_id"])


if __name__ == "__main__":
    unittest.main()
