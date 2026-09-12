import unittest

from worker.diagnostics.visual_evidence import build_visual_evidence


def observation(image_id, element_id, answer_mode="direct_visual"):
    return {"image_id": image_id, "element_id": element_id, "evidence_region": "center", "visible_objects": ["strip"], "visible_text": [], "answer_mode": answer_mode, "prominence": "dominant", "legibility": "clear", "confidence": "high", "source_refs": [image_id]}


class VisualEvidenceTests(unittest.TestCase):
    def test_complete_image_element_matrix_is_ready(self):
        result = build_visual_evidence(image_ids=["img1", "img2"], observations=[observation("img1", "f1"), observation("img2", "f1")], expected_element_ids=["f1"], evidence_version="v1")
        self.assertEqual("ready", result["status"])
        self.assertEqual([], result["missing_image_element"])

    def test_missing_image_is_partial_not_not_seen(self):
        result = build_visual_evidence(image_ids=["img1", "img2"], observations=[observation("img1", "f1")], expected_element_ids=["f1"], evidence_version="v1")
        self.assertEqual("partial", result["status"])
        self.assertEqual([["img2", "f1"]], result["missing_image_element"])

    def test_invalid_enum_or_unknown_scope_fails_closed(self):
        result = build_visual_evidence(image_ids=["img1"], observations=[observation("other", "f1"), {**observation("img1", "f1"), "confidence": "certain"}], expected_element_ids=["f1"], evidence_version="v1")
        self.assertEqual("failed", result["status"])
        self.assertTrue(result["errors"])

    def test_unknown_observation_is_not_judged_ready(self):
        result = build_visual_evidence(image_ids=["img1"], observations=[observation("img1", "f1", "unknown")], expected_element_ids=["f1"], evidence_version="v1")
        self.assertEqual("partial", result["status"])
        self.assertIn("observation_not_judged", result["errors"])


if __name__ == "__main__":
    unittest.main()
