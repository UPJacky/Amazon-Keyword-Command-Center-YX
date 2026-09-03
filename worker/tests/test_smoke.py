import json
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class SmokeTest(unittest.TestCase):
    def test_local_end_to_end_smoke(self):
        process = subprocess.run([sys.executable, str(ROOT / "scripts" / "smoke_test.py")], cwd=ROOT, capture_output=True, text=True, check=True)
        result = json.loads(process.stdout)
        self.assertTrue(result["passed"])
        self.assertEqual(result["network_calls"], 0)


if __name__ == "__main__":
    unittest.main()

