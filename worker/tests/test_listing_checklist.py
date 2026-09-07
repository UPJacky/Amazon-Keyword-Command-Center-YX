import unittest

from worker.diagnostics.listing_checklist import build_checklist, build_image_group, build_listing_diagnostics, diagnose_conversion_gap
from worker.rule_engine.engine import load_default_config


class ListingChecklistTests(unittest.TestCase):
    def test_image_group_is_metadata_only_and_does_not_download(self):
        group = build_image_group([{"url": "https://example.invalid/image.jpg"}], group_id="self-images")
        self.assertEqual(group["provider_calls"], 0)
        self.assertEqual(group["images"][0]["observations"], [])
        self.assertEqual(group["schema_version"], "image-group-0.2")

    def test_checklist_separates_unknown_facts_from_evaluation(self):
        checklist = build_checklist(image_group_id="self-images", competitor_group_id="comp-images")
        self.assertTrue(all(item["status"] == "unknown" for item in checklist["items"]))
        self.assertEqual(checklist["ai_status"], "not_requested")
        self.assertEqual(checklist["schema_version"], "listing-checklist-0.2")

    def test_observations_are_preserved_and_conclusions_require_evidence(self):
        payload = build_listing_diagnostics(
            self_images=[{"url": "https://cdn.example.com/self.jpg", "observations": [{"dimension": "message", "finding": "clear", "evidence": ["image-1"]}], "provider_calls": 1}],
            competitor_images=[], keyword_rows=[], config=load_default_config(),
        )
        self.assertEqual(payload["module_status"]["status"], "ready")
        self.assertEqual(payload["self_images"]["images"][0]["observations"][0]["dimension"], "message")
        self.assertEqual(payload["self_images"]["provider_calls"], 1)
        self.assertEqual(payload["checklist"]["items"][0]["status"], "unknown")

    def test_high_opportunity_low_cvr_references_conversion_checks(self):
        result = diagnose_conversion_gap({"keyword": "led", "market_opportunity_score": 0.9, "cvr": 0.01}, load_default_config())
        self.assertTrue(result["triggered"])
        self.assertEqual(result["checklist_refs"], ["hero_value_prop", "benefit_proof"])


if __name__ == "__main__":
    unittest.main()
