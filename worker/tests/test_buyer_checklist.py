import unittest

from worker.diagnostics.buyer_checklist import build_buyer_checklist


class BuyerChecklistTests(unittest.TestCase):
    def test_caps_at_seven_and_keeps_sources_and_order(self):
        result = build_buyer_checklist(candidates=[{"element_id": f"e{i}", "name": f"要素{i}", "source_refs": [f"s{i}"]} for i in range(9)], confirmation_version="v1")
        self.assertEqual("ready", result["status"])
        self.assertEqual(7, len(result["items"]))
        self.assertEqual("s0", result["items"][0]["source_refs"][0])

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
