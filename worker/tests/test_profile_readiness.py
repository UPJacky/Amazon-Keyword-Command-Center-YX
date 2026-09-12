import unittest

from worker.competitors.profile import COMPARISON_FIELDS, build_competitor_profile


class ProfileReadinessTests(unittest.TestCase):
    def test_missing_own_product_fields_make_profile_partial(self):
        complete = {field: "value" for field in COMPARISON_FIELDS}
        result = build_competitor_profile(
            self_asin="B000000001",
            self_product={"asin": "B000000001"},
            competitors=[{**complete, "asin": asin} for asin in ("B000000002", "B000000003", "B000000004")],
        )
        self.assertEqual("partial", result["module_status"]["status"])
        self.assertTrue(result["self_missing_fields"])


if __name__ == "__main__":
    unittest.main()
