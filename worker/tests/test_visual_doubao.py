import json
import re
import tempfile
import unittest

from worker.providers.base import ProviderAttemptBudget
from worker.providers.cache import ProviderCache
from worker.providers.visual_doubao import DoubaoVisualEvidenceAdapter, VisualCallBudget


def visual_payload(*, action=False):
    result = {
        "visual_evidence": {
            "evidence_version": "visual-v1",
            "expected_element_ids": ["feature-1"],
            "observations": [{
                "image_id": "self-image-1", "element_id": "feature-1", "evidence_region": "center",
                "visible_objects": ["product"], "visible_text": ["dimmable"],
                "answer_mode": "direct_visual", "prominence": "dominant", "legibility": "clear",
                "confidence": "high", "source_refs": ["self-image-1"],
            }],
        }
    }
    if action:
        result["action_group"] = "scale_up"
    return {"output_text": json.dumps(result), "usage": {"output_tokens": 7}}


class FakeTransport:
    def __init__(self):
        self.calls = []

    def call(self, payload):
        self.calls.append(payload)
        return visual_payload()


class VisualDoubaoTests(unittest.TestCase):
    def rows(self):
        return {"asin": "B000000001", "image_urls": ["https://img.example/self.jpg"]}, [
            {"asin": "B000000002", "image_urls": ["https://img.example/competitor.jpg"]}
        ]

    def test_shared_total_attempt_budget_blocks_visual_request(self):
        total = ProviderAttemptBudget(1)
        first_transport = FakeTransport()
        first = DoubaoVisualEvidenceAdapter(
            transport=first_transport, model="vision-model",
            budget=VisualCallBudget(1, 20), attempt_budget=total)
        own, competitors = self.rows()
        first.enrich(self_product=own, competitors=competitors,
                     expected_elements=[{"element_id": "feature-1", "name": "dimmable"}])
        self.assertEqual(1, total.used_attempts)

        second_transport = FakeTransport()
        second = DoubaoVisualEvidenceAdapter(
            transport=second_transport, model="vision-model",
            budget=VisualCallBudget(1, 20), attempt_budget=total)
        with self.assertRaisesRegex(RuntimeError, "TOTAL_PROVIDER_ATTEMPTS_EXHAUSTED"):
            second.enrich(self_product=own, competitors=competitors,
                         expected_elements=[{"element_id": "feature-1", "name": "dimmable"}])
        self.assertEqual([], second_transport.calls)

    def test_structured_visual_call_is_budgeted_and_cached(self):
        with tempfile.TemporaryDirectory() as directory:
            cache = ProviderCache(directory, ttl_seconds=3600)
            first_transport = FakeTransport()
            first = DoubaoVisualEvidenceAdapter(
                transport=first_transport, model="vision-model", budget=VisualCallBudget(1, 20),
                cache=cache, cache_namespace="test")
            own, competitors = self.rows()
            result = first.enrich(self_product=own, competitors=competitors,
                                  expected_elements=[{"element_id": "feature-1", "name": "dimmable"}])
            self.assertEqual(1, len(first_transport.calls))
            self.assertEqual(7, result["provider_usage"]["output_tokens"])
            self.assertRegex(result["provider_usage"]["request_sha256"], r"^[a-f0-9]{64}$")
            self.assertRegex(result["provider_usage"]["response_sha256"], r"^[a-f0-9]{64}$")
            self.assertRegex(result["provider_usage"]["input_images_sha256"], r"^[a-f0-9]{64}$")
            self.assertNotIn("https://img.example/self.jpg", json.dumps(result["provider_usage"]))
            second_transport = FakeTransport()
            second = DoubaoVisualEvidenceAdapter(
                transport=second_transport, model="vision-model", budget=VisualCallBudget(1, 20),
                cache=cache, cache_namespace="test")
            cached = second.enrich(self_product=own, competitors=competitors,
                                   expected_elements=[{"element_id": "feature-1", "name": "dimmable"}])
            self.assertEqual([], second_transport.calls)
            self.assertEqual(1, cached["provider_usage"]["cache_hits"])
            self.assertRegex(cached["provider_usage"]["input_images_sha256"], r"^[a-f0-9]{64}$")

    def test_operational_action_in_model_output_is_rejected(self):
        class ActionTransport:
            def call(self, payload):
                return visual_payload(action=True)

        adapter = DoubaoVisualEvidenceAdapter(
            transport=ActionTransport(), model="vision-model", budget=VisualCallBudget(1, 20))
        own, competitors = self.rows()
        with self.assertRaises(ValueError):
            adapter.enrich(self_product=own, competitors=competitors,
                           expected_elements=[{"element_id": "feature-1", "name": "dimmable"}])

    def test_low_confidence_output_is_partial_and_not_judgement_eligible(self):
        class LowConfidenceTransport:
            def call(self, payload):
                value = visual_payload()
                data = json.loads(value["output_text"])
                data["visual_evidence"]["observations"][0]["confidence"] = "low"
                return {"output_text": json.dumps(data), "usage": {"output_tokens": 1}}

        adapter = DoubaoVisualEvidenceAdapter(
            transport=LowConfidenceTransport(), model="vision-model", budget=VisualCallBudget(1, 20))
        own, competitors = self.rows()
        result = adapter.enrich(self_product=own, competitors=competitors,
                                expected_elements=[{"element_id": "feature-1", "name": "dimmable"}])
        evidence = result["visual_evidence"]
        self.assertEqual("partial", evidence["status"])
        self.assertEqual(0, evidence["coverage"]["judged"])
        self.assertFalse(evidence["observations"][0]["judgement_eligible"])


if __name__ == "__main__":
    unittest.main()
