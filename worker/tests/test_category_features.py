import unittest

from worker.competitors.category_features import (
    build_feature_cleaning_draft,
    category_feature_module_status,
    normalize_category_features,
)


class CategoryFeatureTests(unittest.TestCase):
    def test_normalizes_tutorial_shape_preserving_ratios_and_stable_order(self):
        result = normalize_category_features({
            "analysis_results": [
                {"product_feature": "调光", "product_count_share": "64.2", "monthly_sales_share": 40},
                {"product_feature": "易安装", "product_count_share": 60, "monthly_sales_share": 60},
                {"product_feature": "无效空名", "product_count_share": 1, "monthly_sales_share": 1},
            ],
            "snapshot_version": "s1",
        })
        self.assertEqual(["易安装", "调光", "无效空名"], [row["name"] for row in result["features"]])
        self.assertEqual(64.2, result["features"][1]["product_count_share"])
        self.assertEqual("s1", result["snapshot_version"])
        self.assertEqual("ready", category_feature_module_status(result)["status"])

    def test_empty_or_missing_structure_is_not_zero_success(self):
        for payload in ({}, {"features": []}, {"features": [{"name": ""}]}):
            with self.assertRaises(ValueError):
                normalize_category_features(payload)

    def test_missing_product_fact_becomes_gap_not_exclude(self):
        snapshot = normalize_category_features({"features": [{"feature_id": "f1", "name": "调光", "monthly_sales_share": 50}]})
        draft = build_feature_cleaning_draft(snapshot, self_facts=[])
        self.assertEqual("gap", draft["items"][0]["proposal"])
        self.assertFalse(draft["items"][0]["confirmed"])

    def test_invalid_row_is_partial_and_kept_auditable(self):
        result = normalize_category_features({"features": [{"name": "调光"}, "bad-row"]})
        self.assertEqual([1], result["invalid_rows"])
        self.assertEqual("partial", category_feature_module_status(result)["status"])


if __name__ == "__main__":
    unittest.main()
