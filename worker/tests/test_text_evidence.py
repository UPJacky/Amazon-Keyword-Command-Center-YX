import unittest

from worker.competitors.text_evidence import build_text_evidence_matrix


class TextEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.features = [{"feature_id": "f1", "name": "调光", "english_name": "dimmable"}, {"feature_id": "f2", "name": "易安装", "english_name": "easy to install"}]

    def test_matrix_is_feature_by_asin_and_preserves_confirmation_order(self):
        result = build_text_evidence_matrix(self.features, [
            {"asin": "b000000001", "title": "Dimmable light", "bullet_points": ["easy to install"]},
            {"asin": "B000000002", "title": "Basic light"},
        ], confirmed_feature_ids=["f2", "f1"], confirmation_version="v1")
        self.assertEqual(["f2", "f1"], result["feature_ids"])
        self.assertEqual(["B000000001", "B000000002"], result["asins"])
        self.assertEqual(4, len(result["cells"]))
        self.assertEqual("mentioned", result["cells"][0]["status"])
        self.assertEqual("not_mentioned", result["cells"][1]["status"])
        self.assertEqual("v1", result["cells"][0]["evidence_version"])

    def test_missing_body_is_not_not_mentioned(self):
        result = build_text_evidence_matrix(self.features[:1], [{"asin": "B000000001"}], confirmed_feature_ids=["f1"], confirmation_version="v1")
        self.assertEqual("source_missing", result["cells"][0]["status"])
        self.assertEqual("partial", result["status"])

    def test_unknown_or_duplicate_confirmed_ids_fail_closed(self):
        with self.assertRaises(ValueError):
            build_text_evidence_matrix(self.features, [{"asin": "B000000001", "title": "x"}], confirmed_feature_ids=["f1", "f1"], confirmation_version="v1")
        with self.assertRaises(ValueError):
            build_text_evidence_matrix(self.features, [{"asin": "B000000001", "title": "x"}], confirmed_feature_ids=["unknown"], confirmation_version="v1")


if __name__ == "__main__":
    unittest.main()
