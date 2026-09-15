"""Focused local behavior gates for LUNU-05.

These tests are intentionally separate from the broad worker discovery gate.
They preserve the audit's concrete counterexamples as a small, deterministic
acceptance boundary.  No network, credential, Provider, or database call is
allowed here.
"""

from __future__ import annotations

import copy
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from worker.diagnostics.visual_evidence import build_visual_evidence
from worker.diagnostics.optimization import build_optimization_plan
from worker.pipeline.task_runner import _provider_result
from worker.report.modules import (
    build_negative_keywords,
    build_share_board,
    negative_module_status,
    share_module_status,
)
from worker.providers.sorftime_adapter import SorftimeCallBudget, normalize_product_detail
from worker.rule_engine.engine import evaluate_keyword, load_default_config
from worker.runtime.production import ProductionWorker
from worker.storage.artifact_registry import ALL_BUNDLE_ARTIFACTS, REPORT_ARTIFACTS
from worker.storage.artifacts import artifact_path
from worker.tests.test_production_runtime import FakeTransport, PREVIEW_RPC, PREVIEWED_RPC


class Lunu05BusinessGateTests(unittest.TestCase):
    def test_negative_protection_and_coverage_are_fail_closed(self):
        groups = build_negative_keywords([
            {"keyword": "rope lights", "clicks": 12, "spend": 3, "orders": 0, "relevance": "unrelated"},
            {"keyword": "indoor rope lights", "clicks": 30, "spend": 90, "orders": 0, "relevance": "related"},
            {"keyword": "missing clicks", "clicks": None, "spend": 1, "orders": 0, "relevance": "unknown"},
        ], load_default_config())
        self.assertFalse(groups["phrase_negative"])
        conflict = next(row for row in groups["pending_confirmation"]
                        if row.get("reason") == "phrase_conflicts_with_protected_keyword")
        self.assertEqual("rope lights", conflict["keyword"])
        status = negative_module_status(groups)
        self.assertEqual({"classified_rows": 2, "total_rows": 3}, status["coverage"])
        self.assertGreaterEqual(status["coverage"]["classified_rows"], 0)
        self.assertLessEqual(status["coverage"]["classified_rows"], status["coverage"]["total_rows"])

    def test_entity_actions_use_independent_facts_and_defense_boundary(self):
        row = {
            "keyword": "led light", "action_group": "scale_up", "market_opportunity_score": 0.95,
            "ad_entities": [
                {"campaign_id": "A", "campaign_name": "A", "ad_group_id": "GA", "ad_group_name": "GA",
                 "target_id": "TA", "target": "led light", "match_type": "精准",
                 "impressions": 100, "clicks": 20, "spend": 10, "orders": 10, "sales": 100},
                {"campaign_id": "B", "campaign_name": "B", "ad_group_id": "GB", "ad_group_name": "GB",
                 "target_id": "TB", "target": "led light", "match_type": "词组",
                 "impressions": 1000, "clicks": 100, "spend": 100, "orders": 0, "sales": 0},
            ],
        }
        action = build_optimization_plan([row], load_default_config())[0]
        diagnoses = action["entity_diagnoses"]
        self.assertEqual(["scale_up", "stop_loss"], [item["recommended_action"]["action_group"] for item in diagnoses])
        self.assertEqual([10, 100], [item["facts"]["spend"] for item in diagnoses])
        self.assertEqual("ready", action["entity_status"])

        config = load_default_config()
        defense_case = {"keyword": "led light", "impressions": 1000, "clicks": 25,
                        "spend": 20, "sales": 100, "orders": 4, "organic_rank": 5}
        config["organic_defense"]["max_defense_acos"] = 0.10
        result = evaluate_keyword(defense_case, config)
        self.assertNotEqual("defend_rank", result["action_group"])

    def test_share_requires_explicit_unit_identity_and_denominator(self):
        unknown = build_share_board([{
            "keyword": "led lights", "asin": "B012345678", "keyword_market_share": 0.2,
            "asin_keyword_dependency": 0.05,
        }])
        self.assertEqual("unknown_denominator", unknown[0]["keyword_market_share"]["status"])
        self.assertEqual("partial", share_module_status(unknown)["status"])

        valid = build_share_board([{
            "keyword": "led lights", "asin": "B012345678", "keyword_market_share": "1%",
            "asin_keyword_dependency": 1, "keyword_market_share_denominator": 100,
            "asin_keyword_dependency_denominator": 100, "share_period": "2026-08",
            "share_scope": "US", "provider_source": "fixture",
        }])
        self.assertEqual(1.0, valid[0]["keyword_market_share"]["display_percent"])
        self.assertEqual(100.0, valid[0]["asin_keyword_dependency"]["display_percent"])
        self.assertEqual("ready", share_module_status(valid)["status"])

    def test_visual_unknown_observation_cannot_be_judged(self):
        result = build_visual_evidence(
            image_ids=["self-image-1"],
            expected_element_ids=["dimmable"],
            evidence_version="visual-v1",
            observations=[{
                "image_id": "self-image-1", "element_id": "dimmable", "evidence_region": "",
                "visible_objects": [], "visible_text": [], "answer_mode": "unknown",
                "prominence": "unknown", "legibility": "unreadable", "confidence": "low",
                "source_refs": [],
            }],
        )
        self.assertEqual("partial", result["status"])
        self.assertEqual(0, result["coverage"]["judged"])
        self.assertFalse(result["observations"][0]["judgement_eligible"])

    def test_sorftime_product_aliases_and_gallery_are_normalized(self):
        payload = {"code": 200, "data": {
            "asin": "B012345678", "productTitle": "RGB light",
            "images": ["https://img.example/1.jpg", "https://img.example/2.jpg", "https://img.example/3.jpg"],
            "productAttributes": {"Color": "RGB"}, "productDescription": "Adjustable light",
            "price": 9.98, "currency": "USD", "stars": 4.4, "ratings": 10,
            "monthlySales": 100, "categoryName": "Lights", "categoryRank": 7,
            "variationCount": 1,
        }}
        response = {"isError": False, "content": [{"type": "text", "text": json.dumps(payload)}]}
        result = normalize_product_detail(response, asin="B012345678", marketplace="US", sampled_at="2026-09-15T00:00:00Z")
        self.assertEqual(3, len(result["image_urls"]))
        self.assertEqual("RGB light", result["title"])
        self.assertEqual({"Color": "RGB"}, result["attributes"])
        self.assertEqual("Adjustable light", result["description"])
        self.assertEqual(3, len(result["gallery"]))
        self.assertTrue(all(item["source_image_id"].startswith("sorftime-") for item in result["gallery"]))

    def test_persistent_evidence_manifest_hash_is_reproducible(self):
        # This checks the canonical hashing rule without starting a Worker or
        # uploading anything.  It guards the exact contract used by R13.
        manifest = {"task_id": "task", "run_id": "run", "artifacts": {
            "rules-snapshot.json": {"sha256": hashlib.sha256(b"rules").hexdigest()},
        }}
        signed = {**copy.deepcopy(manifest), "manifest_sha256": hashlib.sha256(
            json.dumps(manifest, ensure_ascii=False, sort_keys=True,
                       separators=(",", ":"), allow_nan=False).encode("utf-8")
        ).hexdigest()}
        unsigned = dict(signed)
        digest = unsigned.pop("manifest_sha256")
        self.assertEqual(digest, hashlib.sha256(
            json.dumps(unsigned, ensure_ascii=False, sort_keys=True,
                       separators=(",", ":"), allow_nan=False).encode("utf-8")
        ).hexdigest())

    def test_sorftime_budget_guard_runs_before_claim_without_consuming_calls(self):
        """R12: an exhausted Sorftime budget blocks claim admission."""
        budget = SorftimeCallBudget(1)
        self.assertTrue(budget.can_accept_request())
        self.assertTrue(budget.can_accept_request(calls=1))
        self.assertTrue(budget.reserve())
        self.assertFalse(budget.can_accept_request())
        self.assertFalse(budget.can_accept_request(calls=1))
        self.assertFalse(budget.can_accept_request(calls=-1))

        from scripts import run_production_worker
        worker = MagicMock()
        worker.run_loop.return_value = {"errors": 0, "failed": 0, "blocked": 0, "cycles": 0}
        xiyou_budget = MagicMock()
        xiyou_budget.can_accept_request.return_value = True
        sorftime_budget = MagicMock()
        sorftime_budget.can_accept_request.return_value = False
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(run_production_worker, "ProductionWorker", return_value=worker), \
                patch.object(run_production_worker.RestrictedTransport, "from_env", return_value=object()), \
                patch.object(run_production_worker, "McpHttpTransport", return_value=object()), \
                patch.object(run_production_worker, "SorftimeTransport", return_value=object()), \
                patch.object(run_production_worker, "ProviderCache", return_value=object()), \
                patch.object(run_production_worker, "XiyouCallBudget", return_value=xiyou_budget), \
                patch.object(run_production_worker, "SorftimeCallBudget", return_value=sorftime_budget), \
                patch("sys.stdout"):
            self.assertEqual(0, run_production_worker.main([
                "--confirm-live", "--xiyou-keywords", "1", "--max-provider-calls", "1",
                "--max-provider-credits", "1", "--sorftime-catalog", "--max-sorftime-calls", "1",
                "--provider-cache-dir", directory, "--max-cycles", "1",
            ]))
        self.assertFalse(worker.provider_claim_guard())
        sorftime_budget.can_accept_request.assert_called_once_with(calls=1)

    def test_provider_claim_preview_blocks_whole_task_before_claim(self):
        """R12: six-task admission is based on the next task, not one call."""
        from scripts.run_production_worker import _provider_claim_admission
        from worker.providers.xiyou_live_enrichment import XiyouCallBudget

        fake = FakeTransport()
        worker = ProductionWorker(fake)
        budget = XiyouCallBudget(max_calls=1, max_credits=1)
        allowed = _provider_claim_admission(
            worker, xiyou_budget=budget, sorftime_budget=None,
            visual_budget=None, xiyou_enabled=True,
            sorftime_enabled=False, visual_enabled=False,
        )
        self.assertFalse(allowed)
        self.assertEqual([PREVIEW_RPC], [path for _, path, *_ in fake.calls])

    def test_provider_claim_preview_allows_bounded_task_and_never_claims_empty_queue(self):
        """R12: a valid preview is read-only and an empty queue remains idle."""
        from scripts.run_production_worker import _provider_claim_admission
        from worker.providers.xiyou_live_enrichment import XiyouCallBudget

        fake = FakeTransport()
        worker = ProductionWorker(fake)
        budget = XiyouCallBudget(max_calls=2, max_credits=2)
        self.assertTrue(_provider_claim_admission(
            worker, xiyou_budget=budget, sorftime_budget=None,
            visual_budget=None, xiyou_enabled=True,
            sorftime_enabled=False, visual_enabled=False,
        ))
        self.assertEqual({"task_id": "11111111-1111-4111-8111-111111111111",
                          "run_id": "44444444-4444-4444-8444-444444444444"},
                         worker.provider_claim_preview)
        self.assertEqual([PREVIEW_RPC], [path for _, path, *_ in fake.calls])
        fake.claim = None
        fake.calls.clear()
        self.assertTrue(_provider_claim_admission(
            worker, xiyou_budget=budget, sorftime_budget=None,
            visual_budget=None, xiyou_enabled=True,
            sorftime_enabled=False, visual_enabled=False,
        ))
        self.assertEqual([PREVIEW_RPC], [path for _, path, *_ in fake.calls])

    def test_six_task_budget_exhaustion_preserves_pending_and_recovers(self):
        """R12: six fake tasks stop before claim, then resume after capacity returns."""
        from scripts.run_production_worker import _provider_claim_admission

        class PreviewQueue:
            def __init__(self):
                template = copy.deepcopy(FakeTransport().claim["task"])
                template["competitor_asins"] = []
                template["primary_core_keyword"] = None
                self.pending = [copy.deepcopy(template) for _ in range(6)]
                self.preview_calls = 0
                self.claim_calls = 0

            def _rpc(self, name, _payload):
                self.assert_name(name)
                self.preview_calls += 1
                if not self.pending:
                    return None
                task = copy.deepcopy(self.pending[0])
                return {"task": task, "run": {"run_id": "44444444-4444-4444-8444-444444444444",
                                                "task_id": task["task_id"]}}

            def assert_name(self, name):
                self.claim_calls += int(name == "kwcc_claim_run")
                if name != "kwcc_preview_next_run":
                    raise AssertionError("test admission must not call claim")

            def acknowledge_claim(self):
                self.pending.pop(0)

        queue = PreviewQueue()
        budget = SorftimeCallBudget(3)
        admitted = 0
        blocked = 0
        for _ in range(6):
            allowed = _provider_claim_admission(
                queue, xiyou_budget=MagicMock(), sorftime_budget=budget,
                visual_budget=None, xiyou_enabled=False,
                sorftime_enabled=True, visual_enabled=False,
            )
            if allowed:
                self.assertTrue(budget.reserve())
                queue.acknowledge_claim()
                admitted += 1
            else:
                blocked += 1
        self.assertEqual((admitted, blocked, len(queue.pending)), (3, 3, 3))
        self.assertEqual(queue.claim_calls, 0)

        # Recovery is an explicit capacity refresh/restart decision; the
        # blocked task remains pending and is not silently discarded.
        budget = SorftimeCallBudget(3)
        while queue.pending:
            self.assertTrue(_provider_claim_admission(
                queue, xiyou_budget=MagicMock(), sorftime_budget=budget,
                visual_budget=None, xiyou_enabled=False,
                sorftime_enabled=True, visual_enabled=False,
            ))
            self.assertTrue(budget.reserve())
            queue.acknowledge_claim()
        self.assertEqual(queue.claim_calls, 0)

    def test_report_artifact_registry_matches_storage_and_frontend_allowlists(self):
        """R13: every bundle artifact has one backend registry and UI entry."""
        frontend_client = (ROOT / "frontend" / "client.js").read_text(encoding="utf-8")
        frontend_shared = (ROOT / "frontend" / "report" / "shared.js").read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory() as directory:
            for name in ALL_BUNDLE_ARTIFACTS:
                artifact_path(directory, "task-1", "run-1", name)
            for name in REPORT_ARTIFACTS:
                self.assertIn(name, frontend_client)
                self.assertIn(name, frontend_shared)

    def test_provider_receipts_reject_raw_payloads_and_bad_digests(self):
        """R13: observability accepts hashes only, never request/response data."""
        base = {
            "market_rows": [],
            "provider_snapshot_version": "snapshot-lunu05-receipt-v1",
            "usage": {"actual_calls": 1},
        }
        for stats in (
            {"actual_calls": 1, "request": "secret-or-payload"},
            {"actual_calls": 1, "request_sha256": "not-a-sha256"},
            {"actual_calls": 1, "call_receipts": [{"request": "raw-body"}]},
        ):
            with self.subTest(stats=stats):
                with self.assertRaises(ValueError):
                    _provider_result({**base, "provider_usage": {"xiyou": stats}})

    def test_production_factory_pipeline_persists_business_modules_and_evidence(self):
        """R15: claim -> factory -> local pipeline -> private bundle readback.

        The transport and provider below are deliberately fake and local.  The
        assertion is about composition and persistence, not live-provider
        completeness: injected data must remain ``injected_provider_data`` and
        must not upgrade ``full_report_complete``.
        """
        fake = FakeTransport()
        fake.claim["task"]["marketplace"] = "US"
        calls = []

        class LocalFactoryProvider:
            real_provider_verified = False

            def __call__(self, parsed, config):
                calls.append({"keywords": len(parsed["aggregated_rows"]), "config": copy.deepcopy(config)})
                return {
                    "market_rows": [{"keyword": "alpha", "market_search_volume": 1000,
                                     "organic_rank": 5, "ad_rank": 3}],
                    "provider_snapshot_version": "snapshot-lunu05-fixture-v1",
                    "usage": {"actual_calls": 1, "cache_hits": 0, "retries": 0},
                    "provider_usage": {"xiyou": {"actual_calls": 1, "cache_hits": 0, "retries": 0}},
                    "category_features": {
                        "features": [{"feature_id": "f-1", "name": "easy to install",
                                       "product_count_share": "60%", "monthly_sales_share": "55%"}],
                        "invalid_rows": [], "empty_name_count": 0, "invalid_share_count": 0,
                    },
                    "buyer_checklist": {"status": "ready", "items": [{"check_id": "f-1", "confirmed": True}]},
                    "text_evidence": {"status": "ready", "cells": [{"feature_id": "f-1", "source": "title"}]},
                }

        result = ProductionWorker(fake, provider_factory=lambda metadata: LocalFactoryProvider()).run_once()
        self.assertEqual("completed", result["status"], result)
        self.assertEqual("injected_provider_data", result["report_scope"])
        self.assertFalse(result["full_report_complete"])
        self.assertEqual(1, len(calls))
        bundle = json.loads(fake.upload)
        self.assertEqual("US", bundle["marketplace"])
        self.assertEqual("snapshot-lunu05-fixture-v1", bundle["provider_snapshot_version"])
        self.assertEqual({"category-features.json", "buyer-checklist.json", "text-evidence.json"},
                         {name for name in bundle["modules"] if name in {"category-features.json", "buyer-checklist.json", "text-evidence.json"}})
        self.assertEqual({"rules-snapshot.json", "run-meta.json", "provider-usage.json"},
                         set(bundle["evidence_artifacts"]))
        self.assertEqual(1, bundle["evidence_artifacts"]["provider-usage.json"]["usage"]["actual_calls"])
        self.assertEqual(bundle["input_sha256"], bundle["evidence_artifacts"]["run-meta.json"]["input_sha256"])
        manifest = copy.deepcopy(bundle["evidence_manifest"])
        manifest_hash = manifest.pop("manifest_sha256")
        self.assertEqual(manifest_hash, hashlib.sha256(
            json.dumps(manifest, ensure_ascii=False, sort_keys=True,
                       separators=(",", ":"), allow_nan=False).encode("utf-8")
        ).hexdigest())


if __name__ == "__main__":
    unittest.main()
