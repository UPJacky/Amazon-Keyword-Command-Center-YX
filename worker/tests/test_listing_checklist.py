import unittest

from worker.diagnostics.listing_checklist import build_checklist, build_image_group, diagnose_conversion_gap
from worker.rule_engine.engine import load_default_config


class ListingChecklistTests(unittest.TestCase):
    def test_image_group_is_metadata_only_and_does_not_download(self):
        group = build_image_group([{"url": "https://example.invalid/image.jpg"}], group_id="self-images")
        self.assertEqual(group["provider_calls"], 0)
        self.assertEqual(group["images"][0]["observations"], [])

    def test_checklist_separates_unknown_facts_from_evaluation(self):
        checklist = build_checklist(image_group_id="self-images", competitor_group_id="comp-images")
        self.assertTrue(all(item["status"] == "unknown" for item in checklist["items"]))
        self.assertEqual(checklist["ai_status"], "not_requested")

    def test_high_opportunity_low_cvr_references_conversion_checks(self):
        result = diagnose_conversion_gap({"keyword": "led", "market_opportunity_score": 0.9, "cvr": 0.01}, load_default_config())
        self.assertTrue(result["triggered"])
        self.assertEqual(result["checklist_refs"], ["hero_value_prop", "benefit_proof"])


if __name__ == "__main__":
    unittest.main()
