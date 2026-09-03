import unittest

from worker.config.config_merge import config_version, effective_config


class ConfigMergeTests(unittest.TestCase):
    def test_precedence_and_nested_merge(self):
        result = effective_config({
            "global": {"acos": {"target": 0.2, "tolerance": 0.3}, "stage": "stable"},
            "store": {"acos": {"tolerance": 0.28}},
            "stage": {"stage": "new"},
            "asin": {"acos": {"target": 0.25}},
            "task": {"temporary": True},
        })
        self.assertEqual(result["acos"], {"target": 0.25, "tolerance": 0.28})
        self.assertEqual(result["stage"], "new")
        self.assertTrue(result["temporary"])

    def test_version_is_stable_and_changes_with_config(self):
        first = config_version({"b": 2, "a": 1})
        second = config_version({"a": 1, "b": 2})
        self.assertEqual(first, second)
        self.assertNotEqual(first, config_version({"a": 1, "b": 3}))


if __name__ == "__main__":
    unittest.main()

