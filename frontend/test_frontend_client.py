"""Run offline Node fake-fetch behavior tests in the existing unittest discovery."""
import shutil
import subprocess
import unittest
from pathlib import Path
from contract_check import has_secret_like_text


class FrontendClientTests(unittest.TestCase):
    def test_secret_guard_exception_does_not_exempt_real_config(self):
        source = (Path(__file__).resolve().parent / "client.js").read_text(encoding="utf-8")
        self.assertFalse(has_secret_like_text(source, "client.js"))
        self.assertTrue(has_secret_like_text(source + "\nconst key = 'sb_secret_fake';", "client.js"))
        self.assertTrue(has_secret_like_text("const key = 'sb_secret_fake';", "public-config.js"))

    def test_node_fake_fetch_contracts(self):
        node = shutil.which("node")
        self.assertIsNotNone(node, "Node is required for frontend behavioral tests")
        root = Path(__file__).resolve().parent
        result = subprocess.run(
            [node, "--test", str(root / "tests" / "client.test.js"), str(root / "tests" / "report-shared.test.js"), str(root / "tests" / "report-modules.test.js")],
            cwd=root, capture_output=True, text=True, encoding="utf-8", timeout=60,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
