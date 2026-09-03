import unittest
from pathlib import Path
from unittest.mock import patch

from worker.security.path_guard import contains_link_or_reparse, is_link_or_reparse


class PathGuardTests(unittest.TestCase):
    def test_missing_path_is_not_marked_as_link(self):
        with patch.object(Path, "stat", side_effect=FileNotFoundError):
            self.assertFalse(is_link_or_reparse(Path("missing")))

    def test_inspection_error_fails_closed(self):
        with patch.object(Path, "stat", side_effect=PermissionError("denied")):
            self.assertTrue(is_link_or_reparse(Path("blocked")))
            self.assertTrue(contains_link_or_reparse(Path("blocked")))


if __name__ == "__main__":
    unittest.main()
