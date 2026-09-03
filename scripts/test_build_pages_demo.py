import tempfile
import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from build_pages_demo import SECRET_PATTERN, audit_demo_output, build

ROOT = Path(__file__).resolve().parents[1]


class PagesDemoTests(unittest.TestCase):
    def test_secret_guard_allows_validation_literals_only(self):
        self.assertIsNone(SECRET_PATTERN.search("value.includes('sb_secret_') || role === 'service_role'"))

    def test_secret_guard_detects_values_and_assignments(self):
        for content in (
            "sb_secret_" + "synthetic00000000", "AKID" + "A" * 28,
            "eyJfake.fake.signature", "-----BEGIN RSA PRIVATE KEY-----",
            '"service_role": "synthetic00000000"',
            "SUPABASE_SERVICE_ROLE_KEY=synthetic00000000",
            "COS_SECRET_KEY=synthetic00000000",
        ):
            with self.subTest(kind=content.split('=')[0][:20]):
                self.assertIsNotNone(SECRET_PATTERN.search(content))

    def test_audit_rejects_secret_value(self):
        with tempfile.TemporaryDirectory() as directory:
            output = build(Path(directory) / "site")
            (output / "frontend" / "client.js").write_text(
                "const key='sb_secret_" + "synthetic00000000';", encoding="utf-8")
            self.assertTrue(any("secret-like content" in error for error in audit_demo_output(output)))

    def test_generated_site_has_safe_local_boundary(self):
        with tempfile.TemporaryDirectory() as directory:
            output = build(Path(directory) / "site")
            self.assertEqual(audit_demo_output(output), [])

    def test_demo_build_has_canonical_offline_config(self):
        from build_pages_demo import DEMO_PUBLIC_CONFIG
        with tempfile.TemporaryDirectory() as directory:
            output = build(Path(directory) / "site")
            config = output / "frontend/public-config.js"
            self.assertEqual(DEMO_PUBLIC_CONFIG, config.read_text(encoding="utf-8"))
            config.write_text('window.KWCC_PUBLIC_CONFIG={mode:"live"};', encoding="utf-8")
            self.assertTrue(any("canonical offline" in error for error in audit_demo_output(output)))

    def test_audit_rejects_external_url(self):
        with tempfile.TemporaryDirectory() as directory:
            output = build(Path(directory) / "site")
            (output / "frontend" / "login.html").write_text(
                (output / "frontend" / "login.html").read_text(encoding="utf-8")
                + '<a href="https://example.invalid">external</a>',
                encoding="utf-8",
            )
            self.assertTrue(any("external URL" in error for error in audit_demo_output(output)))

    def test_audit_rejects_broken_local_reference(self):
        with tempfile.TemporaryDirectory() as directory:
            output = build(Path(directory) / "site")
            (output / "frontend" / "login.html").write_text(
                (output / "frontend" / "login.html").read_text(encoding="utf-8")
                + '<a href="missing.html">missing</a>',
                encoding="utf-8",
            )
            self.assertTrue(any("broken local HTML reference" in error for error in audit_demo_output(output)))


    def test_build_rejects_symlinked_output_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "target"
            target.mkdir()
            link = Path(directory) / "site-link"
            try:
                link.symlink_to(target, target_is_directory=True)
            except (OSError, NotImplementedError):
                self.skipTest("symbolic links unavailable")
            with self.assertRaises(ValueError):
                build(link)

    def test_build_rejects_symlinked_source_file(self):
        source = ROOT / "frontend" / "app.js"
        backup = source.with_suffix(".js.pages-test-backup")
        try:
            source.rename(backup)
            try:
                source.symlink_to(backup)
            except (OSError, NotImplementedError):
                self.skipTest("symbolic links unavailable")
            with tempfile.TemporaryDirectory() as directory:
                with self.assertRaises(ValueError):
                    build(Path(directory) / "site")
        finally:
            if source.is_symlink() or source.exists():
                source.unlink()
            if backup.exists():
                backup.rename(source)

    def test_audit_does_not_read_symlink_target(self):
        with tempfile.TemporaryDirectory() as directory:
            output = build(Path(directory) / "site")
            outside = Path(directory) / "outside.txt"
            outside.write_text("service_role=do-not-read", encoding="utf-8")
            link = output / "frontend" / "external.txt"
            try:
                link.symlink_to(outside)
            except (OSError, NotImplementedError):
                self.skipTest("symbolic links unavailable")
            errors = audit_demo_output(output)
            self.assertTrue(any("symlink is not allowed" in error for error in errors))
            self.assertFalse(any("secret-like content: frontend/external.txt" in error for error in errors))

    def test_audit_rejects_symlinked_output_root(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "target"
            output = build(target)
            link = Path(directory) / "site-link"
            try:
                link.symlink_to(output, target_is_directory=True)
            except (OSError, NotImplementedError):
                self.skipTest("symbolic links unavailable")
            self.assertTrue(any("output directory path" in error for error in audit_demo_output(link)))


if __name__ == "__main__":
    unittest.main()
