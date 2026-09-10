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
        self.assertEqual(payload["module_status"]["status"], "partial")
        self.assertEqual(payload["self_images"]["observation_status"], "partial")
        self.assertEqual(payload["self_images"]["images"][0]["observations"][0]["dimension"], "message")
        self.assertEqual(payload["self_images"]["provider_calls"], 1)
        self.assertEqual(payload["checklist"]["items"][0]["status"], "unknown")

    def test_high_opportunity_low_cvr_references_conversion_checks(self):
        result = diagnose_conversion_gap({"keyword": "led", "market_opportunity_score": 0.9, "cvr": 0.01}, load_default_config())
        self.assertTrue(result["triggered"])
        self.assertEqual(result["checklist_refs"], ["hero_value_prop", "benefit_proof"])

    def test_valid_visual_matrix_is_projected_but_unconfirmed_checklist_stays_partial(self):
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
        payload = build_listing_diagnostics(
            self_images=[{"url": "https://cdn.example.com/self.jpg", "image_id": "self-image-1"}],
            competitor_images=[], keyword_rows=[], config=load_default_config(),
            visual_evidence=evidence,
        )
        self.assertEqual("partial", payload["module_status"]["status"])
        self.assertEqual("visual_evidence_incomplete_or_checklist_unconfirmed", payload["module_status"]["reason"])
        self.assertEqual("self-image-1", payload["self_images"]["images"][0]["observations"][0]["image_id"])

    def test_one_competitor_comparison_and_one_brief_per_self_image_are_bound(self):
        evidence = {
            "expected_element_ids": ["hero_value_prop"], "evidence_version": "visual-v1",
            "observations": [{
                "image_id": "self-image-1", "element_id": "hero_value_prop",
                "evidence_region": "center", "visible_objects": ["product"],
                "visible_text": [], "answer_mode": "direct_visual",
                "prominence": "dominant", "legibility": "clear", "confidence": "high",
                "source_refs": ["self-image-1"],
            }, {
                "image_id": "B000000002-image-1", "element_id": "hero_value_prop",
                "evidence_region": "center", "visible_objects": ["product"],
                "visible_text": [], "answer_mode": "direct_visual",
                "prominence": "dominant", "legibility": "clear", "confidence": "high",
                "source_refs": ["B000000002-image-1"],
            }],
        }
        evaluations = {item["check_id"]: {"status": "pass", "evidence": [item["check_id"]]} for item in build_checklist(image_group_id="self-images")["items"]}
        payload = build_listing_diagnostics(
            self_images=[{"image_id": "self-image-1", "url": "https://cdn.example.com/self.jpg"}],
            competitor_images=[{"image_id": "B000000002-image-1", "url": "https://cdn.example.com/comp.jpg"}],
            competitor_asins=["B000000002"], keyword_rows=[], config=load_default_config(),
            visual_evidence=evidence, checklist_evaluations=evaluations,
            competitor_comparisons=[{
                "competitor_asin": "B000000002", "element_id": "hero_value_prop", "status": "弱",
                "target_self_image_id": "self-image-1", "reference_competitor_image_id": "B000000002-image-1",
                "evidence": ["B000000002-image-1"], "borrowing_method": "保留结构并强化卖点",
                "specific_change": "提高核心卖点层级",
            }],
            image_briefs=[{
                "self_image_id": "self-image-1", "label": "主图", "existing_expression": "展示产品主体",
                "weak_elements": ["核心卖点层级"], "keep_content": ["产品主体"],
                "composition": "主体居中，保留合规背景", "subject": "灯带与控制器",
                "text_hierarchy": "先产品识别，再核心卖点", "english_copy_draft": "RGB LED Strip Lights",
                "keywords": ["led lights"], "references": [{"competitor_asin": "B000000002", "image_id": "B000000002-image-1", "reason": "卖点层级参考"}],
                "truth_constraints": ["只写已确认功能"],
            }],
        )
        self.assertEqual("ready", payload["visual_brief"]["module_status"]["status"])
        self.assertEqual("ready", payload["module_status"]["status"])
        self.assertEqual("B000000002-image-1", payload["visual_brief"]["briefs"][0]["references"][0]["image_id"])

    def test_brief_without_reference_or_unknown_comparison_stays_partial(self):
        payload = build_listing_diagnostics(
            self_images=[{"image_id": "self-image-1", "url": "https://cdn.example.com/self.jpg"}],
            competitor_images=[{"image_id": "B000000002-image-1", "url": "https://cdn.example.com/comp.jpg"}],
            competitor_asins=["B000000002"], keyword_rows=[], config=load_default_config(),
            competitor_comparisons=[{
                "competitor_asin": "B000000002", "element_id": "hero_value_prop", "status": "未知",
                "target_self_image_id": "self-image-1", "reference_competitor_image_id": "B000000002-image-1",
            }],
            image_briefs=[{"self_image_id": "self-image-1", "label": "主图", "references": []}],
        )
        self.assertEqual("partial", payload["visual_brief"]["module_status"]["status"])
        self.assertEqual("comparison_or_brief_incomplete", payload["visual_brief"]["module_status"]["reason"])


if __name__ == "__main__":
    unittest.main()
