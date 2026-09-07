import tempfile
import unittest
import sys
import hashlib
import json
import shutil
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

from build_pages_demo import SECRET_PATTERN, audit_demo_output, build
from build_pages_demo import CANONICAL_ROUTES, EXTERNAL_URL_PATTERN, LEGACY_ROUTES, REPORT_PAGES, expected_demo_files
import build_pages_demo as pages_demo
import build_workbench_demo as workbench_demo

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

    def test_six_report_pages_and_shared_scripts_are_packaged_canonically(self):
        with tempfile.TemporaryDirectory() as directory:
            output = build(Path(directory) / "site")
            self.assertEqual(len(REPORT_PAGES), 6)
            for name in CANONICAL_ROUTES:
                with self.subTest(route=name):
                    source = ROOT / "frontend" / name
                    self.assertTrue(source.is_file())
                    self.assertEqual((output / name).read_bytes(), source.read_bytes())
            self.assertEqual({p.relative_to(output).as_posix() for p in output.rglob("*") if p.is_file()},
                             expected_demo_files())
            self.assertEqual(audit_demo_output(output), [])

    def test_historical_aliases_resolve_to_canonical_pages_and_keep_query_and_hash(self):
        with tempfile.TemporaryDirectory() as directory:
            output = build(Path(directory) / "site")
            for name, target in LEGACY_ROUTES.items():
                with self.subTest(alias=name):
                    alias = output / name
                    content = alias.read_text(encoding="utf-8")
                    self.assertIn(f'href="{target}"', content)
                    self.assertIn(f"location.replace({json.dumps(target)} + location.search + location.hash)", content)
                    self.assertTrue((alias.parent / target).resolve().is_file())
            self.assertIn("frontend/tool/index.html", LEGACY_ROUTES)
            for name in REPORT_PAGES:
                self.assertIn(f"frontend/report/{name}.html", LEGACY_ROUTES)

    def test_three_new_demo_artifacts_are_packaged_without_image_urls(self):
        with tempfile.TemporaryDirectory() as directory:
            output = build(Path(directory) / "site")
            for name in workbench_demo.ARTIFACT_FILES:
                with self.subTest(artifact=name):
                    target = output / "data/golden/market-demo-modules" / name
                    self.assertEqual(target.read_bytes(), (workbench_demo.DEFAULT_OUTPUT / name).read_bytes())
                    content = target.read_text(encoding="utf-8")
                    self.assertIsNone(EXTERNAL_URL_PATTERN.search(content))
                    self.assertIsNone(SECRET_PATTERN.search(content))
                    payload = json.loads(content)
                    self.assertTrue(payload["demo"])
                    self.assertTrue(payload["fixture_source"])
                    self.assertEqual(payload["provider_calls"], 0)

    def test_audit_rejects_raw_and_unreviewed_files(self):
        with tempfile.TemporaryDirectory() as directory:
            output = build(Path(directory) / "site")
            (output / "data/golden/market-demo-modules/raw.csv").write_text("raw", encoding="utf-8")
            (output / "report/unreviewed.json").write_text("{}", encoding="utf-8")
            errors = audit_demo_output(output)
            self.assertTrue(any("forbidden file:" in error and "raw.csv" in error for error in errors))
            self.assertTrue(any("outside static allowlist:" in error and "unreviewed.json" in error for error in errors))

    def test_build_copies_only_reviewed_demo_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "source"
            sources = {*(f"frontend/{name}" for name in pages_demo.FRONTEND_FILES),
                       *(f"frontend/{name}" for name in CANONICAL_ROUTES),
                       *(f"data/golden/{folder}/{name}" for folder, names in pages_demo.DEMO_FILES.items() for name in names),
                       "rules/defaults/stable.json"}
            for name in sources:
                (root / name).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(ROOT / name, root / name)
            for name in ("data/golden/market-demo-modules/raw.csv", "frontend/report/unreviewed.js"):
                (root / name).write_text("sb_secret_" + "synthetic00000000", encoding="utf-8")
            with patch.object(pages_demo, "ROOT", root):
                output = build(Path(directory) / "site")
            self.assertFalse((output / "data/golden/market-demo-modules/raw.csv").exists())
            self.assertFalse((output / "report/unreviewed.js").exists())
            self.assertEqual(audit_demo_output(output), [])

    def test_audit_rejects_missing_module_data_and_script(self):
        with tempfile.TemporaryDirectory() as directory:
            output = build(Path(directory) / "site")
            for name in ("report/shared.js", "data/golden/market-demo-modules/competitors.json"):
                (output / name).unlink()
                self.assertIn(f"missing allowlisted file: {name}", audit_demo_output(output))

    def test_audit_checks_single_quoted_navigation_with_query_and_fragment(self):
        with tempfile.TemporaryDirectory() as directory:
            output = build(Path(directory) / "site")
            page = output / "frontend/login.html"
            original = page.read_text(encoding="utf-8")
            page.write_text(original + "<a href='report/rank.html?task=demo#rows'>Rank</a>", encoding="utf-8")
            self.assertEqual(audit_demo_output(output), [])
            page.write_text(original + "<a href='report/missing.html?task=demo#rows'>Missing</a>", encoding="utf-8")
            self.assertTrue(any("broken local HTML reference" in error for error in audit_demo_output(output)))


class WorkbenchDemoTests(unittest.TestCase):
    def test_rebuild_matches_checked_in_artifacts_and_is_deterministic_offline(self):
        inputs = (workbench_demo.COMPETITOR_INPUT, workbench_demo.LISTING_INPUT,
                  workbench_demo.REPORT_INPUT, workbench_demo.CONFIG_INPUT)
        before = {name: (ROOT / name).read_bytes() for name in inputs}
        with tempfile.TemporaryDirectory() as directory, patch("socket.create_connection", side_effect=AssertionError("network forbidden")) as connect:
            output = workbench_demo.build(Path(directory) / "modules")
            first = {name: (output / name).read_bytes() for name in workbench_demo.ARTIFACT_FILES}
            workbench_demo.build(output)
            self.assertEqual({path.name for path in output.iterdir()}, set(workbench_demo.ARTIFACT_FILES))
            for name, content in first.items():
                with self.subTest(artifact=name):
                    self.assertEqual(content, (output / name).read_bytes())
                    # A Windows checkout may convert LF to CRLF.
                    self.assertEqual(content, (workbench_demo.DEFAULT_OUTPUT / name).read_bytes().replace(b"\r\n", b"\n"))
                    payload = json.loads(content)
                    self.assertIs(payload["demo"], True)
                    self.assertIs(payload["local_only"], True)
                    for metric in ("provider_calls", "network_calls", "external_calls"):
                        self.assertEqual(payload[metric], 0)
                    self.assertIn(payload["fixture_source"], inputs)
                    self.assertTrue(payload["fixture_builders"])
                    for source in payload["fixture_inputs"]:
                        self.assertEqual(source["sha256"], hashlib.sha256(before[source["path"]].replace(b"\r\n", b"\n")).hexdigest())
            connect.assert_not_called()
        self.assertEqual(before, {name: (ROOT / name).read_bytes() for name in inputs})

    def test_competitor_projection_preserves_fixture_metadata(self):
        payload = workbench_demo.build_payloads()["competitors.json"]
        source = json.loads((ROOT / workbench_demo.COMPETITOR_INPUT).read_text(encoding="utf-8"))
        self.assertEqual(payload["schema_version"], "competitors-0.2")
        self.assertEqual(payload["snapshot_version"], source["snapshot_version"])
        self.assertEqual(payload["self_asin"], source["self_asin"])
        self.assertEqual(len(payload["competitors"]), len(source["competitors"]))
        for actual, original in zip(payload["competitors"], source["competitors"]):
            for key in ("asin", "brand", "title"):
                self.assertEqual(actual[key], original[key])
            self.assertEqual(actual["image_urls"], [])
        self.assertNotIn("self_images", payload)

    def test_listing_keeps_image_ids_and_unknown_evidence(self):
        payload = workbench_demo.build_payloads()["listing-diagnostics.json"]
        self.assertEqual(payload["schema_version"], "listing-diagnostics-0.1")
        for key in ("self_images", "competitor_images"):
            self.assertEqual(len(payload[key]["images"]), 1)
            image = payload[key]["images"][0]
            self.assertEqual(image["image_id"], "image-1")
            self.assertEqual(image["position"], 1)
            self.assertIsNone(image["url"])
            self.assertEqual(image["observations"], [])
        self.assertEqual(payload["checklist"]["ai_status"], "not_requested")
        for item in payload["checklist"]["items"]:
            self.assertEqual(item["status"], "unknown")
            self.assertEqual(item["evidence"], [])
        diagnosis = payload["conversion_diagnostics"][0]
        self.assertTrue(diagnosis["triggered"])
        self.assertEqual(diagnosis["reason"], "high_opportunity_low_cvr")
        self.assertEqual(diagnosis["facts"], {"market_opportunity_score": 0.9, "cvr": 0.01})

    def test_optimization_preserves_all_report_facts_rules_and_actions(self):
        payload = workbench_demo.build_payloads()["optimization-plan.json"]
        report = json.loads((ROOT / workbench_demo.REPORT_INPUT).read_text(encoding="utf-8"))
        self.assertEqual(payload["schema_version"], "optimization-plan-0.2")
        self.assertFalse(payload["ai_may_change_action"])
        self.assertEqual(len(payload["actions"]), len(report["rows"]))
        for action, row in zip(payload["actions"], report["rows"]):
            for key in ("keyword", "action_group", "rule_hits", "next_action_text"):
                self.assertEqual(action[key], row[key])
            for key, value in action["data_facts"].items():
                self.assertEqual(value, row.get(key))
            self.assertEqual(action["ai_status"], "not_requested")
            self.assertFalse(action["ai_may_change_action"])
            self.assertEqual(action["config_refs"]["config_version"], report["config_version"])

    def test_only_placeholder_image_urls_are_removed_other_unsafe_content_fails(self):
        for field, value in (("image_urls", ["https://cdn.invalid/product.jpg"]),
                             ("title", "https://example.invalid/not-an-image"),
                             ("brand", "sb_secret_" + "synthetic00000000")):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as directory:
                root = Path(directory) / "source"
                for name in (workbench_demo.COMPETITOR_INPUT, workbench_demo.LISTING_INPUT,
                             workbench_demo.REPORT_INPUT, workbench_demo.CONFIG_INPUT):
                    (root / name).parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(ROOT / name, root / name)
                source = root / workbench_demo.COMPETITOR_INPUT
                payload = json.loads(source.read_text(encoding="utf-8"))
                payload["competitors"][0][field] = value
                source.write_text(json.dumps(payload), encoding="utf-8")
                output = Path(directory) / "output"
                with patch.object(workbench_demo, "ROOT", root):
                    with self.assertRaisesRegex(ValueError, "unsafe public demo content"):
                        workbench_demo.build(output)
                self.assertFalse(output.exists())

    def test_builder_does_not_overwrite_non_demo_data(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            target = output / "competitors.json"
            target.write_text('{"private_record": true}', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "non-demo artifact"):
                workbench_demo.build(output)
            self.assertEqual(target.read_text(encoding="utf-8"), '{"private_record": true}')
            self.assertFalse((output / "listing-diagnostics.json").exists())


if __name__ == "__main__":
    unittest.main()
