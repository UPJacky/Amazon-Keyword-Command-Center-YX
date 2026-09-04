"""Offline release-boundary tests; all mutations stay in temporary directories."""

import base64
import contextlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_pages_demo as demo
import build_pages_live as live

ROOT = Path(__file__).resolve().parents[1]
PROJECT_REF = "abcdefghijklmnopqrst"
ORIGIN = "https://" + PROJECT_REF + ".supabase.co"


def segment(value):
    raw = json.dumps(value, separators=(",", ":")).encode() if not isinstance(value, bytes) else value
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def anon_key(**overrides):
    payload = {"iss": "supabase", "ref": PROJECT_REF, "role": "anon", "iat": 1, "exp": 4102444800}
    payload.update(overrides)
    return ".".join((segment({"alg": "HS256", "typ": "JWT"}), segment(payload), segment(b"s" * 32)))


def config(**overrides):
    result = {"mode": "live", "liveEnabled": True, "supabaseUrl": ORIGIN,
              "publicKey": "sb_publishable_" + "synthetic" * 4,
              "gatewayUrl": ORIGIN + "/functions/v1/kwcc-gateway"}
    result.update(overrides)
    return result


class ConfigTests(unittest.TestCase):
    def test_accepts_publishable_and_anon(self):
        for key in (config()["publicKey"], anon_key()):
            self.assertEqual(live.validate_public_config(config(publicKey=key))["publicKey"], key)

    def test_rejects_wrong_project_privileged_and_user_tokens(self):
        keys = (anon_key(ref="z" * 20), anon_key(role="service_role"), anon_key(role="authenticated"),
                "sb_secret_" + "synthetic" * 4, "", "eyJfake.fake.signature",
                config()["publicKey"] + "\n", config()["publicKey"] + "';alert(1)", None)
        for key in keys:
            with self.subTest(kind=type(key).__name__), self.assertRaises(ValueError) as caught:
                live.validate_public_config(config(publicKey=key))
            if key:
                self.assertNotIn(key, str(caught.exception))

    def test_rejects_jwt_ambiguous_or_extended_claims_and_bad_signature_shape(self):
        header = segment({"alg": "HS256", "typ": "JWT"})
        payload = segment({"iss": "supabase", "ref": PROJECT_REF, "role": "anon"})
        duplicate = segment(b'{"iss":"supabase","ref":"abcdefghijklmnopqrst","role":"service_role","role":"anon"}')
        keys = (anon_key(iss="untrusted"), anon_key(exp=True), anon_key(iat=-1),
                anon_key(password="synthetic-secret"),
                ".".join((header, duplicate, segment(b"s" * 32))),
                ".".join((segment({"alg": "none", "typ": "JWT"}), payload, segment(b"s" * 32))),
                ".".join((header, payload, "short")),
                ".".join((header, payload + "=", segment(b"s" * 32))))
        for key in keys:
            with self.subTest(), self.assertRaises(ValueError):
                live.validate_public_config(config(publicKey=key))

    def test_requires_exact_fields_and_explicit_live_switches(self):
        for changes in ({"mode": "demo"}, {"liveEnabled": "true"}, {"liveEnabled": 1},
                        {"liveEnabled": False}, {"extra": "ignored?"}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                live.validate_public_config(config(**changes))
        for field in live.CONFIG_FIELDS:
            candidate = config()
            candidate.pop(field)
            with self.assertRaises(ValueError):
                live.validate_public_config(candidate)

    def test_requires_pure_supabase_https_origin(self):
        for origin in (ORIGIN + "/", ORIGIN + "/rest/v1", ORIGIN + ":443", ORIGIN + "?x=1",
                       ORIGIN + "#x", ORIGIN + ".evil.invalid", ORIGIN.replace("https:", "http:"),
                       ORIGIN.replace("https://", "https://user@"), "https://example.invalid",
                       " https://" + PROJECT_REF + ".supabase.co", ORIGIN + "\n", None):
            with self.subTest(), self.assertRaises(ValueError):
                live.validate_public_config(config(supabaseUrl=origin))

    def test_requires_exact_same_origin_gateway(self):
        for gateway in ("https://evil.invalid/functions/v1/kwcc-gateway",
                        "https://" + "z" * 20 + ".supabase.co/functions/v1/kwcc-gateway",
                        ORIGIN + "/functions/v1/other", ORIGIN + "/functions/v1/kwcc-gateway/",
                        ORIGIN + "/functions/v1/kwcc-gateway?x=1", "", None):
            with self.subTest(), self.assertRaises(ValueError):
                live.validate_public_config(config(gatewayUrl=gateway))


class LivePagesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Snapshot only the demo builder's declared inputs. Never edit shared frontend files.
        cls.snapshot = tempfile.TemporaryDirectory()
        cls.source = Path(cls.snapshot.name) / "source"
        names = {*("frontend/" + name for name in demo.FRONTEND_FILES),
                 *("frontend/" + name for name in demo.CANONICAL_ROUTES),
                 *(f"data/golden/{folder}/{name}" for folder, files in demo.DEMO_FILES.items() for name in files),
                 "rules/defaults/stable.json"}
        for name in names:
            target = cls.source / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / name, target)
        with patch.object(demo, "ROOT", cls.source):
            cls.baseline = live.build(Path(cls.snapshot.name) / "baseline", config())

    @classmethod
    def tearDownClass(cls):
        cls.snapshot.cleanup()

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.output = self.directory / "site"
        shutil.copytree(self.baseline, self.output)

    def audit(self):
        return live.audit_live_output(self.output, config())

    def test_exact_allowlist_and_no_fixture_or_raw_inputs(self):
        self.assertEqual(self.audit(), [])
        self.assertEqual({p.relative_to(self.output).as_posix() for p in self.output.rglob("*") if p.is_file()},
                         live.expected_live_files())
        self.assertEqual(live.expected_live_files(), demo.expected_demo_files() - {
            f"data/golden/{folder}/{name}" for folder, names in demo.DEMO_FILES.items() for name in names})
        self.assertFalse((self.output / "data").exists())
        self.assertEqual({p.relative_to(self.output).as_posix() for p in self.output.rglob("*.json")},
                         {"rules/defaults/stable.json"})
        for name in live.PUBLIC_CONFIG_FILES:
            self.assertEqual((self.output / name).read_bytes(), live.render_public_config(config()).encode())

    def test_build_and_anon_audit_are_offline(self):
        candidate = config(publicKey=anon_key())
        with patch.object(demo, "ROOT", self.source), \
                patch("socket.create_connection", side_effect=AssertionError("network forbidden")) as connect:
            result = live.build(self.directory / "anon", candidate)
            self.assertEqual(live.audit_live_output(result, candidate), [])
            connect.assert_not_called()
        # Existing global scanner still rejects the same anon token everywhere else.
        self.assertIsNotNone(demo.SECRET_PATTERN.search(candidate["publicKey"]))

    def test_rejects_fixture_raw_secret_and_unexpected_files(self):
        for name in ("data/golden/market-demo-report/master-table.json", "raw.csv", "raw.xlsx",
                     ".env", ".env.production", "private.pem", "report/extra.json"):
            target = self.output / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text('{"demo":true}', encoding="utf-8")
            with self.subTest(name=name):
                self.assertIn(f"file outside static allowlist: {name}", self.audit())
            target.unlink()

    def test_rejects_unexpected_empty_directory(self):
        (self.output / "data" / "golden").mkdir(parents=True)
        self.assertTrue(any("directory outside static allowlist" in e for e in self.audit()))

    def test_never_copies_unlisted_env_or_secrets_from_source(self):
        isolated = self.directory / "source"
        shutil.copytree(self.source, isolated)
        for name in (".env", "frontend/.env.production", "frontend/key.pem",
                     "data/golden/market-demo-report/raw.csv"):
            (isolated / name).write_text("sb_secret_" + "synthetic" * 4, encoding="utf-8")
        with patch.object(demo, "ROOT", isolated):
            result = live.build(self.directory / "clean", config())
        self.assertEqual(live.audit_live_output(result, config()), [])

    def test_approved_urls_and_keys_are_rejected_outside_config(self):
        target = self.output / "client.js"
        original = target.read_text(encoding="utf-8")
        for value, message in ((ORIGIN, "external URL"), (config()["gatewayUrl"], "external URL"),
                               (anon_key(), "secret-like content"),
                               (config()["publicKey"], "secret-like content"),
                               ("sb_secret_" + "synthetic" * 4, "secret-like content")):
            target.write_text(original + "\n// " + value, encoding="utf-8")
            with self.subTest():
                self.assertIn(f"{message}: client.js", self.audit())

    def test_tampered_config_is_rejected_in_both_locations(self):
        replacements = (live.render_public_config(config()) + "// added script\n",
                        live.render_public_config(config(publicKey=anon_key())),
                        live.render_public_config(config()).replace("kwcc-gateway", "other"),
                        demo.DEMO_PUBLIC_CONFIG,
                        'window.KWCC_PUBLIC_CONFIG={"publicKey":"sb_secret_' + 'synthetic00000000"};')
        for name in live.PUBLIC_CONFIG_FILES:
            for replacement in replacements:
                (self.output / name).write_text(replacement, encoding="utf-8")
                with self.subTest(name=name):
                    self.assertIn(f"public configuration differs from approved config: {name}", self.audit())
            (self.output / name).write_bytes(live.render_public_config(config()).encode())

    def test_rejects_missing_files_and_non_utf8(self):
        (self.output / "report/shared.js").unlink()
        (self.output / "client.js").write_bytes(b"\xff\xfe")
        self.assertIn("missing allowlisted file: report/shared.js", self.audit())
        self.assertIn("file cannot be audited as UTF-8: client.js", self.audit())

    def test_html_references_preserve_queries_and_detect_broken_links(self):
        page = self.output / "frontend/login.html"
        original = page.read_text(encoding="utf-8")
        page.write_text(original + "<a href='../report/rank.html?task=abc#rows'>Rank</a>", encoding="utf-8")
        self.assertEqual(self.audit(), [])
        for reference in ("missing.html", "../data/golden/market-demo-report/master-table.json"):
            page.write_text(original + f"<a href='{reference}'>Broken</a>", encoding="utf-8")
            self.assertIn("broken local HTML reference: frontend/login.html", self.audit())

    def test_rejects_html_escape_and_external_references(self):
        page = self.output / "frontend/login.html"
        original = page.read_text(encoding="utf-8")
        for reference in ("../../outside.html", "%2e%2e/%2e%2e/outside.html",
                          "//evil.invalid/a", "javascript:alert(1)", ORIGIN, "/absolute.html"):
            page.write_text(original + f"<a href='{reference}'>Unsafe</a>", encoding="utf-8")
            with self.subTest(reference=reference):
                self.assertTrue(any("HTML reference escapes output" in e for e in self.audit()))

    def test_invalid_config_and_dirty_output_do_not_overwrite(self):
        before = (self.output / "client.js").read_bytes()
        with self.assertRaises(ValueError):
            live.build(self.output, config())
        with self.assertRaises(ValueError):
            live.build(self.directory / "invalid", config(publicKey=anon_key(role="service_role")))
        self.assertFalse((self.directory / "invalid").exists())
        self.assertEqual(before, (self.output / "client.js").read_bytes())

    def test_unsafe_source_fails_before_creating_destination(self):
        isolated = self.directory / "unsafe-source"
        shutil.copytree(self.source, isolated)
        with (isolated / "frontend/app.js").open("a", encoding="utf-8") as stream:
            stream.write("\nconst secret='sb_secret_" + "synthetic00000000';")
        with patch.object(demo, "ROOT", isolated), self.assertRaisesRegex(ValueError, "staging audit"):
            live.build(self.directory / "rejected", config())
        self.assertFalse((self.directory / "rejected").exists())

    def test_link_guard_rejects_source_output_and_config_without_reading(self):
        guard = demo._contains_symlink
        source = self.source / "frontend/app.js"
        with patch.object(demo, "ROOT", self.source), \
                patch.object(demo, "_contains_symlink", side_effect=lambda p: p == source or guard(p)):
            with self.assertRaisesRegex(ValueError, "symbolic link"):
                live.build(self.directory / "guarded", config())
        with patch.object(demo, "_contains_symlink", return_value=True):
            with self.assertRaises(ValueError):
                live.build(self.directory / "linked", config())
            self.assertIn("output directory path must not contain a symbolic link", self.audit())
        target = self.output / "frontend/public-config.js"
        original_read = Path.read_bytes
        def read_checked(path):
            if path == target:
                raise AssertionError("must not read linked target")
            return original_read(path)
        with patch.object(demo, "_contains_symlink", side_effect=lambda p: p == target or guard(p)), \
                patch.object(Path, "read_bytes", read_checked):
            self.assertIn("symlink is not allowed: frontend/public-config.js", self.audit())

    def test_actual_symlink_is_not_traversed_or_read(self):
        outside = self.directory / "outside"
        outside.mkdir()
        (outside / "secret.js").write_text("sb_secret_" + "synthetic00000000", encoding="utf-8")
        linked = self.output / "linked"
        try:
            linked.symlink_to(outside, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("OS symbolic-link privilege unavailable; mocked fail-closed guards covered separately")
        self.assertIn("symlink is not allowed: linked", self.audit())
        self.assertFalse(any("secret.js" in e for e in self.audit()))
        with self.assertRaises(ValueError):
            live.build(linked / "output", config())

    def test_cli_environment_build_audit_and_no_key_disclosure(self):
        candidate = config(publicKey=anon_key())
        environment = {"KWCC_MODE": "live", "KWCC_LIVE_ENABLED": "true",
                       "KWCC_SUPABASE_URL": ORIGIN, "KWCC_GATEWAY_URL": candidate["gatewayUrl"],
                       "KWCC_PUBLIC_KEY": candidate["publicKey"]}
        output = self.directory / "cli"
        for extra in ([], ["--audit-only"]):
            capture = io.StringIO()
            with patch.dict(os.environ, environment, clear=True), patch.object(demo, "ROOT", self.source), \
                    contextlib.redirect_stdout(capture):
                result = live.main(["--output", str(output), *extra])
            self.assertEqual(result, 0)
            self.assertNotIn(candidate["publicKey"], capture.getvalue())
            summary = json.loads(capture.getvalue())
            self.assertTrue(summary["passed"])
            self.assertEqual(summary["file_count"], len(live.expected_live_files()))
            self.assertTrue(summary["local_only"])
            self.assertFalse(summary["published"])
            self.assertEqual(summary["network_calls"], 0)
            self.assertEqual(summary["external_calls"], 0)
        environment["KWCC_PUBLIC_KEY"] = "sb_secret_" + "synthetic00000000"
        capture = io.StringIO()
        with patch.dict(os.environ, environment, clear=True), contextlib.redirect_stdout(capture):
            self.assertEqual(live.main(["--output", str(output), "--audit-only"]), 1)
        self.assertNotIn(environment["KWCC_PUBLIC_KEY"], capture.getvalue())
        with patch.dict(os.environ, {}, clear=True), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(live.main(["--output", str(output), "--audit-only"]), 1)

    def test_cli_process_failure_is_redacted(self):
        key = "sb_secret_" + "synthetic00000000"
        environment = dict(os.environ, KWCC_MODE="live", KWCC_LIVE_ENABLED="true",
                           KWCC_SUPABASE_URL=ORIGIN, KWCC_GATEWAY_URL=config()["gatewayUrl"], KWCC_PUBLIC_KEY=key)
        command = [sys.executable, str(ROOT / "scripts/build_pages_live.py"), "--output", str(self.output)]
        result = subprocess.run(command, env=environment, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 1)
        self.assertFalse(json.loads(result.stdout)["passed"])
        self.assertNotIn(key, result.stdout + result.stderr)
        result = subprocess.run(command + ["--unexpected", key], env=environment,
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 2)
        self.assertNotIn(key, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
