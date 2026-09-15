import unittest

from worker.diagnostics.buyer_checklist import build_buyer_checklist


class BuyerChecklistTests(unittest.TestCase):
    def test_caps_at_seven_and_keeps_sources_and_order(self):
        result = build_buyer_checklist(candidates=[{"element_id": f"e{i}", "name": f"要素{i}", "source_refs": [f"s{i}"]} for i in range(9)], confirmation_version="v1")
        self.assertEqual("draft", result["status"])
        self.assertEqual("confirmation_required", result["reason"])
        self.assertEqual(7, len(result["items"]))
        self.assertEqual("s0", result["items"][0]["source_refs"][0])

    def test_structured_confirmation_is_required_for_ready(self):
        candidates = [{"element_id": f"e{i}", "name": f"要素{i}", "source_refs": [f"s{i}"]} for i in range(2)]
        confirmation = {"confirmation_id": "c1", "object_id": "buyer-checklist", "version": "v1",
                       "status": "confirmed", "task_id": "task-1", "store_id": "store-1",
                       "self_asin": "B012345678", "input_hash": "a" * 64,
                       "confirmed_feature_ids": ["e0", "e1"]}
        result = build_buyer_checklist(candidates=candidates, confirmation_version="v1", confirmation=confirmation)
        self.assertEqual("ready", result["status"])
        self.assertTrue(all(item["confirmed"] for item in result["items"]))
        self.assertTrue(result["confirmation_valid"])

    def test_invalid_confirmation_scope_stays_draft(self):
        confirmation = {"object_id": "buyer-checklist", "version": "v1", "status": "confirmed",
                       "task_id": "task-1", "store_id": "store-1", "self_asin": "B012345678",
                       "input_hash": "a" * 64, "confirmed_feature_ids": ["other"]}
        result = build_buyer_checklist(candidates=[{"element_id": "e1", "name": "调光", "source_refs": ["s1"]}],
                                       confirmation_version="v1", confirmation=confirmation)
        self.assertEqual("draft", result["status"])
        self.assertEqual("confirmation_items_mismatch", result["reason"])
        self.assertFalse(result["items"][0]["confirmed"])

    def test_no_source_is_not_presented_as_confirmed_fact(self):
        result = build_buyer_checklist(candidates=[{"element_id": "e1", "name": "调光"}], confirmation_version=None)
        self.assertEqual("draft", result["status"])
        self.assertEqual("source_missing", result["items"][0]["evidence_status"])
        self.assertFalse(result["items"][0]["confirmed"])

    def test_empty_candidates_are_not_success(self):
        result = build_buyer_checklist(candidates=[])
        self.assertEqual("not_generated", result["status"])
        self.assertEqual([], result["items"])


if __name__ == "__main__":
    unittest.main()
