import unittest

from worker.diagnostics.visual_brief import build_visual_brief


class VisualBriefTests(unittest.TestCase):
    def _common(self):
        return {
            "self_image_ids": ["self-image-1"],
            "competitor_image_ids": ["B000000002-image-1"],
            "competitor_asins": ["B000000002"],
            "expected_element_ids": ["hero_value_prop"],
        }

    def test_binds_one_competitor_and_explicit_reference_images(self):
        result = build_visual_brief(
            **self._common(),
            comparisons=[{
                "competitor_asin": "B000000002", "element_id": "hero_value_prop", "status": "到位",
                "target_self_image_id": "self-image-1", "reference_competitor_image_id": "B000000002-image-1",
                "evidence": ["B000000002-image-1"], "specific_change": "保留层级",
            }],
            briefs=[{
                "self_image_id": "self-image-1", "label": "主图", "existing_expression": "产品主体",
                "references": [{"competitor_asin": "B000000002", "image_id": "B000000002-image-1", "reason": "表达层级"}],
                "truth_constraints": ["只写已确认功能"],
            }],
        )
        self.assertEqual("ready", result["module_status"]["status"])
        self.assertEqual("one_competitor_per_row", result["comparison_scope"])
        self.assertEqual("B000000002-image-1", result["briefs"][0]["references"][0]["image_id"])

    def test_unknown_or_missing_self_brief_is_partial(self):
        result = build_visual_brief(
            **self._common(),
            comparisons=[{
                "competitor_asin": "B000000002", "element_id": "hero_value_prop", "status": "未知",
                "target_self_image_id": "self-image-1", "reference_competitor_image_id": "B000000002-image-1",
            }],
            briefs=[],
        )
        self.assertEqual("partial", result["module_status"]["status"])
        self.assertEqual(0, result["coverage"]["self_images_briefed"])

    def test_unknown_competitor_or_image_is_rejected(self):
        with self.assertRaises(ValueError):
            build_visual_brief(**self._common(), comparisons=[{
                "competitor_asin": "B000000003", "element_id": "hero_value_prop", "status": "到位",
                "target_self_image_id": "self-image-1", "reference_competitor_image_id": "B000000002-image-1",
                "evidence": ["x"],
            }])


if __name__ == "__main__":
    unittest.main()
