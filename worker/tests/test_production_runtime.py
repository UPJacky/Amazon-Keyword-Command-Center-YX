"""Offline production-boundary tests. No real HTTP/Provider credentials."""

import copy
import hashlib
import io
import json
import os
import signal
import socket
import subprocess
import sys
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import Mock, patch

from worker.pipeline.task_runner import run_task
from worker.runtime.production import (
    MAX_INPUT_BYTES, ProductionWorker, RestrictedTransport, RuntimeFailure,
    _NoRedirect, build_effective_config,
)

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "data/fixtures/sample_dynamic_columns.csv"
XLSX = ROOT / "data/fixtures/商品推广_搜索词_报告_LED演示.xlsx"
TASK = "11111111-1111-4111-8111-111111111111"
STORE = "22222222-2222-4222-8222-222222222222"
USER = "33333333-3333-4333-8333-333333333333"
RUN = "44444444-4444-4444-8444-444444444444"
TOKEN = "55555555-5555-4555-8555-555555555555"
RPC = "/rest/v1/rpc/kwcc_claim_run"
JSON_HEADERS = {"Content-Type": "application/json"}


def encoded(value):
    return json.dumps(value).encode()


class FakeTransport:
    def __init__(self, fixture=FIXTURE):
        self.input = fixture.read_bytes()
        self.claim = {"task": {
            "task_id": TASK, "store_id": STORE, "created_by": USER,
            "self_asin": "B012345678", "product_stage": "stable", "strategy_id": None,
            "input_file_path": f"{STORE}/{USER}/{TASK}/input{fixture.suffix}",
            "input_file_hash": hashlib.sha256(self.input).hexdigest(), "task_config_override": {},
        }, "run": {"run_id": RUN, "task_id": TASK, "lease_token": TOKEN}, "config": None}
        self.calls, self.finishes = [], []
        self.upload = None
        self.upload_path = None
        self.heartbeat_ok = True
        self.heartbeats = 0
        self.beat_during_provider = threading.Event()
        self.provider_active = threading.Event()
        self.fail_upload = False
        self.wrong_readback = False
        self.lose_after_upload = False
        self.finish_result = True
        self.fail_finish = False

    def request(self, method, path, *, body=None, headers=None, max_response_bytes=None):
        self.calls.append((method, path, body, headers, max_response_bytes))
        if path == RPC:
            return encoded(self.claim)
        if path.endswith("kwcc_heartbeat_run"):
            self.heartbeats += 1
            if self.provider_active.is_set():
                self.beat_during_provider.set()
            return encoded(self.heartbeat_ok)
        if path.endswith("kwcc_finish_run"):
            receipt = json.loads(body)
            if receipt["p_status"] == "failed":
                reason = receipt["p_failure_reason"]
                assert set(reason) == {"code", "stage", "retryable"}
                assert reason["retryable"] is False
                assert reason["code"] in {
                    "INPUT_INVALID", "INPUT_HASH_MISMATCH", "INPUT_SIZE_MISMATCH", "INPUT_DOWNLOAD_FAILED",
                    "RECONCILIATION_FAILED", "CONFIG_INVALID", "COMPETITOR_PROFILE_INVALID",
                    "PROVIDER_ENRICHMENT_FAILED", "REPORT_GENERATION_FAILED", "REPORT_UPLOAD_FAILED", "UNEXPECTED_TASK_ERROR",
                }
                assert reason["stage"] in {"task", "worker", "ingestion", "reconciliation", "config",
                                            "competitors", "provider", "report", "storage"}
            self.finishes.append(receipt)
            if self.fail_finish:
                raise OSError("SERVER-SECRET-DO-NOT-EXPOSE")
            return encoded(self.finish_result)
        if path.startswith("/storage/v1/object/authenticated/inputs/"):
            return self.input
        if path.startswith("/storage/v1/object/reports/"):
            if self.fail_upload:
                raise OSError("SERVER-SECRET-DO-NOT-EXPOSE")
            self.upload, self.upload_path = body, path
            if self.lose_after_upload:
                self.heartbeat_ok = False
            return encoded({"Key": "ignored"})
        if path.startswith("/storage/v1/object/authenticated/reports/"):
            return b"corrupt" if self.wrong_readback else self.upload
        raise AssertionError("Unexpected request")


class ProductionRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.socket_guard = patch.object(socket, "create_connection", side_effect=AssertionError("network forbidden"))
        self.socket_guard.start()
        self.addCleanup(self.socket_guard.stop)

    def assert_failure(self, transport, code):
        result = ProductionWorker(transport).run_once()
        self.assertEqual("failed", result["status"], result)
        self.assertEqual(code, result["failure_reason"]["code"])
        self.assertEqual(1, len(transport.finishes))
        self.assertEqual("failed", transport.finishes[0]["p_status"])
        self.assertIsNone(transport.finishes[0]["p_report_path"])
        self.assertNotIn("SERVER-SECRET", json.dumps(result) + json.dumps(transport.finishes))
        return result

    def test_default_runtime_never_reads_credentials_or_uses_network(self):
        with patch.dict(os.environ, {"SUPABASE_URL": "invalid", "SUPABASE_SERVICE_ROLE_KEY": "SECRET"}), \
                patch.object(RestrictedTransport, "from_env", side_effect=AssertionError("env read")):
            self.assertEqual({"status": "disabled", "network_calls": 0}, ProductionWorker().run_once())
            stats = ProductionWorker().run_loop(max_cycles=2, poll_interval=0.001)
            self.assertEqual(2, stats["disabled"])
            self.assertEqual(0, stats["network_calls"])

    def test_real_csv_pipeline_bundle_and_completion_order(self):
        fake = FakeTransport()
        originals, local_paths = [], []

        def capture(*args, **kwargs):
            result = run_task(*args, **kwargs)
            originals.append(json.loads(Path(result.report_path).read_text(encoding="utf-8")))
            local_paths.extend((Path(args[0]), Path(result.report_path)))
            return result

        with patch("worker.runtime.production.run_task", side_effect=capture):
            result = ProductionWorker(fake).run_once()
        self.assertEqual("completed", result["status"], result)
        self.assertTrue(all(not path.exists() for path in local_paths))
        bundle = json.loads(fake.upload)
        for field, value in originals[0].items():
            self.assertEqual(value, bundle[field])
        self.assertEqual(TASK, bundle["task_id"])
        self.assertEqual(RUN, bundle["run_id"])
        self.assertEqual(2, bundle["summary"]["keyword_count"])
        self.assertEqual({"rank-benchmark.json", "negative-keywords.json", "optimization-plan.json"}, set(bundle["modules"]))
        self.assertNotIn("listing.json", bundle["modules"])
        self.assertEqual("B012345678", bundle["self_asin"])
        self.assertEqual(STORE, bundle["store_id"])
        self.assertEqual("stable", bundle["product_stage"])
        self.assertNotIn("marketplace", bundle)
        self.assertEqual("ad_only", bundle["report_scope"])
        self.assertFalse(bundle["full_report_complete"])
        self.assertEqual("not_requested", bundle["provider_evidence"]["status"])
        self.assertFalse(bundle["provider_evidence"]["real_provider_verified"])
        self.assertIsNone(bundle["provider_snapshot_version"])
        self.assertRegex(result["report_path"], rf"^{TASK}/{RUN}/report-[0-9a-f]{{48}}\.json$")
        events = [path for _method, path, *_rest in fake.calls]
        upload = events.index(fake.upload_path)
        readback = events.index("/storage/v1/object/authenticated/reports/" + result["report_path"])
        finish = events.index("/rest/v1/rpc/kwcc_finish_run")
        self.assertLess(upload, readback)
        self.assertLess(readback, finish)
        self.assertEqual({"Content-Type": "application/json", "x-upsert": "false"}, fake.calls[upload][3])
        receipt = fake.finishes[0]
        self.assertEqual("completed", receipt["p_status"])
        self.assertEqual(result["report_path"], receipt["p_report_path"])
        for field in ("rule_version", "config_version", "provider_snapshot_version"):
            self.assertEqual(bundle[field], receipt[f"p_{field}"])
        self.assertEqual({"p_run_id", "p_lease_token", "p_status", "p_report_path", "p_failure_reason",
                          "p_rule_version", "p_config_version", "p_provider_snapshot_version"}, set(receipt))

    def test_real_xlsx_fixture_runs_existing_pipeline(self):
        fake = FakeTransport(XLSX)
        result = ProductionWorker(fake).run_once()
        self.assertEqual("completed", result["status"], result)
        bundle = json.loads(fake.upload)
        self.assertEqual(91, bundle["summary"]["keyword_count"])
        self.assertTrue(bundle["reconciliation"]["passed"])

    def test_factory_receives_only_bound_task_metadata_after_hash_validation(self):
        fake = FakeTransport()
        fake.claim['task']['marketplace'] = 'US'
        callback = Mock(return_value={'market_rows': [], 'provider_snapshot_version': 'snapshot-test', 'usage': {'actual_calls': 0}})
        factory = Mock(return_value=callback)
        result = ProductionWorker(fake, provider_factory=factory).run_once()
        self.assertEqual('completed', result['status'], result)
        factory.assert_called_once_with({'task_id': TASK, 'store_id': STORE, 'self_asin': 'B012345678', 'product_stage': 'stable', 'marketplace': 'US'})
        callback.assert_called_once()
        self.assertEqual('US', json.loads(fake.upload)['marketplace'])
        self.assertEqual('injected_provider_data', result['report_scope'])
        fake = FakeTransport()
        fake.claim['task']['input_file_hash'] = '0' * 64
        factory.reset_mock()
        self.assertEqual('failed', ProductionWorker(fake, provider_factory=factory).run_once()['status'])
        factory.assert_not_called()

    def test_factory_failure_has_safe_reason_and_never_uploads(self):
        fake = FakeTransport()
        result = ProductionWorker(fake, provider_factory=Mock(side_effect=ValueError('PRIVATE-DETAIL'))).run_once()
        self.assertEqual('failed', result['status'])
        self.assertEqual('PROVIDER_ENRICHMENT_FAILED', fake.finishes[0]['p_failure_reason']['code'])
        self.assertNotIn('PRIVATE-DETAIL', json.dumps(result))
        self.assertIsNone(fake.upload)
        with self.assertRaises(RuntimeFailure):
            ProductionWorker(fake, provider_factory=lambda task: None, provider_enricher=lambda p,c: None)

    def test_hash_mismatch_prevents_pipeline_and_upload(self):
        fake = FakeTransport()
        fake.claim["task"]["input_file_hash"] = "0" * 64
        with patch("worker.runtime.production.run_task") as pipeline:
            self.assert_failure(fake, "INPUT_HASH_MISMATCH")
            pipeline.assert_not_called()
        self.assertIsNone(fake.upload)

    def test_cross_task_store_user_and_encoded_paths_rejected_before_get(self):
        for path in (f"{STORE}/{USER}/{RUN}/input.csv", f"{USER}/{USER}/{TASK}/input.csv",
                     f"{STORE}/{STORE}/{TASK}/input.csv", "../input.csv", "C:/input.csv",
                     f"inputs/{STORE}/{USER}/{TASK}/input.csv", f"{STORE}/{USER}/{TASK}/%69nput.csv",
                     f"{STORE}/{USER}/{TASK}/input.csv?x=1", "https://example.com/input.csv"):
            with self.subTest(path=path):
                fake = FakeTransport()
                fake.claim["task"]["input_file_path"] = path
                self.assert_failure(fake, "INPUT_INVALID")
                self.assertFalse(any(call[0] == "GET" for call in fake.calls))

    def test_optional_input_size_and_limit(self):
        for value in (True, -1, 0, "188", MAX_INPUT_BYTES + 1):
            with self.subTest(size=value):
                fake = FakeTransport()
                fake.claim["task"]["input_file_size"] = value
                self.assert_failure(fake, "INPUT_INVALID")
        fake = FakeTransport()
        fake.claim["task"]["input_file_size_bytes"] = len(fake.input) + 1
        self.assert_failure(fake, "INPUT_SIZE_MISMATCH")
        fake = FakeTransport()
        fake.claim["task"]["input_size"] = len(fake.input) + 1
        self.assert_failure(fake, "INPUT_SIZE_MISMATCH")
        fake = FakeTransport()
        fake.claim["task"]["input_file_size"] = len(fake.input)
        self.assertEqual("completed", ProductionWorker(fake).run_once()["status"])
        fake = FakeTransport()
        fake.input = b"x" * (MAX_INPUT_BYTES + 1)
        self.assert_failure(fake, "RESPONSE_TOO_LARGE")

    def test_upload_failure_has_no_readback_or_completed_finish(self):
        fake = FakeTransport()
        fake.fail_upload = True
        self.assert_failure(fake, "REPORT_UPLOAD_FAILED")
        self.assertFalse(any("authenticated/reports" in c[1] for c in fake.calls))
        self.assertEqual(1, sum(c[1].startswith("/storage/v1/object/reports/") for c in fake.calls))

    def test_corrupt_readback_never_completes(self):
        fake = FakeTransport()
        fake.wrong_readback = True
        self.assert_failure(fake, "REPORT_HASH_MISMATCH")

    def test_initial_lease_loss_does_not_download_or_finish(self):
        fake = FakeTransport()
        fake.heartbeat_ok = False
        result = ProductionWorker(fake).run_once()
        self.assertEqual("LEASE_LOST", result["failure_reason"]["code"])
        self.assertEqual(2, len(fake.calls))
        self.assertEqual([], fake.finishes)

    def test_claim_that_arrives_after_local_lease_deadline_is_not_processed(self):
        fake = FakeTransport()
        with patch("worker.runtime.production.time.monotonic", side_effect=[0, 4]):
            result = ProductionWorker(fake, lease_seconds=3).run_once()
        self.assertEqual("LEASE_LOST", result["failure_reason"]["code"])
        self.assertEqual(1, len(fake.calls))
        self.assertEqual([], fake.finishes)

    def test_heartbeat_transport_failure_is_not_retried(self):
        fake = FakeTransport()
        original = fake.request

        def request(method, path, **kwargs):
            if path.endswith("kwcc_heartbeat_run"):
                fake.heartbeats += 1
                raise OSError("SERVER-SECRET")
            return original(method, path, **kwargs)

        fake.request = request
        result = ProductionWorker(fake).run_once()
        self.assertEqual("LEASE_LOST", result["failure_reason"]["code"])
        self.assertEqual(1, fake.heartbeats)
        self.assertEqual([], fake.finishes)

    def test_lease_loss_after_upload_never_finishes(self):
        fake = FakeTransport()
        fake.lose_after_upload = True
        result = ProductionWorker(fake).run_once()
        self.assertEqual("LEASE_LOST", result["failure_reason"]["code"])
        self.assertTrue(result["pending"])
        self.assertEqual([], fake.finishes)

    def test_slow_provider_has_independent_heartbeat(self):
        fake = FakeTransport()

        def provider(parsed, config):
            fake.provider_active.set()
            self.assertTrue(fake.beat_during_provider.wait(2), "heartbeat must run while provider blocks")
            return {"market_rows": [], "provider_snapshot_version": "snapshot-fake-empty", "usage": {"actual_calls": 0}}

        result = ProductionWorker(fake, heartbeat_interval=0.01, provider_enricher=provider).run_once()
        self.assertEqual("completed", result["status"], result)
        self.assertGreaterEqual(fake.heartbeats, 3)
        evidence = json.loads(fake.upload)["provider_evidence"]
        self.assertEqual("no_market_data", evidence["status"])
        self.assertFalse(evidence["real_provider_verified"])

    def test_loss_during_provider_cannot_finish_or_upload(self):
        fake = FakeTransport()

        def provider(parsed, config):
            fake.heartbeat_ok = False
            fake.provider_active.set()
            self.assertTrue(fake.beat_during_provider.wait(2))
            return {"market_rows": [], "provider_snapshot_version": "snapshot-fake", "usage": {"actual_calls": 0}}

        result = ProductionWorker(fake, heartbeat_interval=0.01, provider_enricher=provider).run_once()
        self.assertEqual("LEASE_LOST", result["failure_reason"]["code"])
        self.assertEqual([], fake.finishes)
        self.assertIsNone(fake.upload)

    def test_provider_exception_is_sanitized(self):
        fake = FakeTransport()
        result = ProductionWorker(fake, provider_enricher=Mock(side_effect=ValueError("SERVER-SECRET"))).run_once()
        self.assertEqual("PROVIDER_ENRICHMENT_FAILED", result["failure_reason"]["code"])
        self.assertNotIn("SERVER-SECRET", json.dumps(result) + json.dumps(fake.finishes))

    def test_input_transport_failure_uses_rpc_allowlisted_reason(self):
        fake = FakeTransport()
        original = fake.request

        def request(method, path, **kwargs):
            if "/authenticated/inputs/" in path:
                raise OSError("SERVER-SECRET")
            return original(method, path, **kwargs)

        fake.request = request
        self.assert_failure(fake, "INPUT_DOWNLOAD_FAILED")
        self.assertEqual({"code": "INPUT_DOWNLOAD_FAILED", "stage": "ingestion", "retryable": False},
                         fake.finishes[0]["p_failure_reason"])

    def test_existing_competitor_artifact_and_actual_marketplace_are_bundled(self):
        fake = FakeTransport()
        fake.claim["task"]["marketplace"] = "CA"
        profile = {"self_asin": "B012345678", "marketplace": "CA", "competitors": [
            {"asin": "B012345671"}, {"asin": "B012345672"}, {"asin": "B012345673"}]}
        result = ProductionWorker(fake, competitor_profile=profile).run_once()
        self.assertEqual("completed", result["status"], result)
        bundle = json.loads(fake.upload)
        self.assertEqual("CA", bundle["marketplace"])
        self.assertEqual(3, len(bundle["modules"]["competitors.json"]["competitors"]))
        self.assertNotIn("listing.json", bundle["modules"])
        self.assertTrue(all(row["my_organic_rank"] is None for row in bundle["modules"]["rank-benchmark.json"]["rows"]))

    def test_invalid_local_master_contract_is_never_uploaded(self):
        fake = FakeTransport()

        def invalid(*args, **kwargs):
            result = run_task(*args, **kwargs)
            path = Path(result.report_path)
            content = json.loads(path.read_text(encoding="utf-8"))
            content["rows"] = {}
            path.write_text(json.dumps(content), encoding="utf-8")
            return result

        with patch("worker.runtime.production.run_task", side_effect=invalid):
            self.assert_failure(fake, "REPORT_INVALID")
        self.assertIsNone(fake.upload)

    def test_rerun_uses_another_pipeline_random_filename(self):
        first, second = FakeTransport(), FakeTransport()
        a, b = ProductionWorker(first).run_once(), ProductionWorker(second).run_once()
        self.assertEqual("completed", a["status"])
        self.assertEqual("completed", b["status"])
        self.assertNotEqual(a["report_path"], b["report_path"])

    def test_finish_ambiguity_and_false_result_never_send_second_finish(self):
        for failure in (True, False):
            fake = FakeTransport()
            fake.fail_finish = failure
            fake.finish_result = False
            result = ProductionWorker(fake).run_once()
            self.assertEqual("error", result["status"])
            self.assertTrue(result["pending"])
            self.assertTrue(result["finish_attempted"])
            self.assertEqual(1, len(fake.finishes))
            self.assertNotIn("SERVER-SECRET", json.dumps(result))

    def test_rpc_requires_null_object_and_boolean_not_truthiness(self):
        fake = FakeTransport()
        fake.claim = None
        self.assertEqual("idle", ProductionWorker(fake).run_once()["status"])
        for bad in ([], True, {}, {"run": {"run_id": RUN, "lease_token": "../bad"}}):
            fake = FakeTransport()
            fake.claim = bad
            self.assertEqual("RPC_INVALID", ProductionWorker(fake).run_once()["failure_reason"]["code"])
            self.assertEqual([], fake.finishes)
        fake = FakeTransport()
        fake.heartbeat_ok = "true"
        self.assertEqual("LEASE_LOST", ProductionWorker(fake).run_once()["failure_reason"]["code"])

    def test_effective_config_stage_strategy_task_and_stable_version(self):
        task = FakeTransport().claim["task"]
        task["product_stage"] = "new"
        task["task_config_override"] = {"acos": {"target": 0.32}, "config_version": "ignored"}
        strategy = {"acos": {"target": 0.31, "tolerance": 0.55}, "config_version": "ignored-too"}
        original = copy.deepcopy(strategy)
        cfg = build_effective_config(task, strategy)
        self.assertEqual(0.32, cfg["acos"]["target"])
        self.assertEqual(0.55, cfg["acos"]["tolerance"])
        self.assertEqual(0.60, cfg["acos"]["break_even"])
        self.assertEqual("new", cfg["product_stage"])
        self.assertEqual(original, strategy)
        task["task_config_override"]["config_version"] = "arbitrary"
        self.assertEqual(cfg, build_effective_config(task, strategy))
        self.assertRegex(cfg["config_version"], r"^cfg-[0-9a-f]{16}$")

    def test_bad_config_rejected_before_download(self):
        for strategy in ([], {"product_stage": "new"}, {"acos": {"target": "SECRET"}}, {"acos": {"target": float("nan")}}):
            fake = FakeTransport()
            fake.claim["config"] = strategy
            # Non-standard JSON NaN is rejected before a valid claim is trusted.
            result = ProductionWorker(fake).run_once()
            self.assertIn(result["failure_reason"]["code"], ("CONFIG_INVALID", "RPC_INVALID"))
            self.assertIsNone(fake.upload)
            self.assertFalse(any(call[0] == "GET" for call in fake.calls))

    def test_stop_during_pipeline_withholds_finish_and_cleans_temporary_input(self):
        fake, stop = FakeTransport(), threading.Event()
        inputs = []

        def capture(*args, **kwargs):
            inputs.append(Path(args[0]))
            stop.set()
            raise RuntimeError("SERVER-SECRET")

        with patch("worker.runtime.production.run_task", side_effect=capture):
            result = ProductionWorker(fake, stop_event=stop).run_once()
        self.assertEqual("STOP_REQUESTED", result["failure_reason"]["code"])
        self.assertEqual([], fake.finishes)
        self.assertTrue(all(not p.exists() for p in inputs))

    def test_loop_continues_after_failed_task_and_stops_on_signal_callback(self):
        fake = FakeTransport()
        fake.claim["task"]["input_file_hash"] = "0" * 64
        worker = ProductionWorker(fake)
        events = []

        def on_cycle(result):
            events.append(result["status"])
            if len(events) == 1:
                fake.claim = None
            else:
                worker.stop_event.set()

        stats = worker.run_loop(max_cycles=4, poll_interval=0.001, on_cycle=on_cycle)
        self.assertEqual(["failed", "idle"], events)
        self.assertTrue(stats["stopped"])

    def test_cli_bounded_process_defaults_to_zero_network(self):
        process = subprocess.run([sys.executable, "-B", str(ROOT / "scripts/run_production_worker.py"),
                                  "--max-cycles", "2", "--poll-interval", "0.001"],
                                 cwd=ROOT, capture_output=True, text=True, timeout=10)
        self.assertEqual(0, process.returncode, process.stderr)
        summary = json.loads(process.stdout.splitlines()[-1])
        self.assertEqual(2, summary["cycles"])
        self.assertEqual(2, summary["disabled"])
        self.assertEqual(0, summary["network_calls"])
        self.assertFalse(summary["live"])

    def test_cli_sigint_handler_stops_loop_and_restores_handlers(self):
        from scripts.run_production_worker import main
        handlers = {}

        def register(sig, handler):
            previous = handlers.get(sig, signal.SIG_DFL)
            handlers[sig] = handler
            return previous

        original = ProductionWorker.run_once

        def once(worker):
            handlers[signal.SIGINT](signal.SIGINT, None)
            return original(worker)

        with patch("scripts.run_production_worker.signal.signal", side_effect=register), \
                patch.object(ProductionWorker, "run_once", once), patch("sys.stdout", new_callable=io.StringIO) as output:
            self.assertEqual(0, main(["--poll-interval", "0.001"]))
            summary = json.loads(output.getvalue().splitlines()[-1])
        self.assertTrue(summary["stopped"])
        self.assertEqual(signal.SIG_DFL, handlers[signal.SIGINT])

    def test_cli_live_requires_ad_only_acknowledgment_before_env(self):
        from scripts.run_production_worker import main
        with patch.object(RestrictedTransport, "from_env") as env, patch("sys.stdout", new_callable=io.StringIO) as output:
            self.assertEqual(1, main(["--confirm-live", "--max-cycles", "1"]))
            env.assert_not_called()
            self.assertIn("AD_ONLY_CONFIRMATION_REQUIRED", output.getvalue())

    def test_cli_live_explicit_opt_in_still_uses_fake_transport_for_test(self):
        from scripts.run_production_worker import main
        fake = FakeTransport()
        fake.claim = None
        with patch.object(RestrictedTransport, "from_env", return_value=fake) as env, \
                patch("sys.stdout", new_callable=io.StringIO) as output:
            self.assertEqual(0, main(["--confirm-live", "--ad-only", "--max-cycles", "1"]))
            env.assert_called_once_with(confirm_live=True, timeout=20)
            summary = json.loads(output.getvalue().splitlines()[-1])
        self.assertEqual("ad_only", summary["report_scope"])
        self.assertFalse(summary["full_report_complete"])

    def test_cli_xiyou_mode_requires_explicit_bounded_budget(self):
        from scripts.run_production_worker import main
        for arguments in (["--xiyou-keywords", "1"], ["--xiyou-keywords", "11", "--max-provider-calls", "1", "--max-provider-credits", "1"],
                          ["--ad-only", "--xiyou-keywords", "1", "--max-provider-calls", "1", "--max-provider-credits", "1"],
                          ["--max-provider-calls", "1"]):
            with self.subTest(arguments=arguments), patch("sys.stdout", new_callable=io.StringIO):
                self.assertEqual(1, main(arguments + ["--max-cycles", "1"]))

    def test_cli_xiyou_live_composes_factory_without_exposing_settings(self):
        from scripts.run_production_worker import main
        fake = FakeTransport(); fake.claim = None
        with patch.object(RestrictedTransport, "from_env", return_value=fake), \
                patch("scripts.run_production_worker.McpHttpTransport") as transport, \
                patch.dict(os.environ, {"XYDC_MCP_URL": "https://provider.invalid/mcp", "XYDC_MCP_TOKEN": "private-test-token"}), \
                patch("sys.stdout", new_callable=io.StringIO) as output:
            self.assertEqual(0, main(["--confirm-live", "--xiyou-keywords", "2",
                "--max-provider-calls", "3", "--max-provider-credits", "3", "--max-cycles", "1"]))
            transport.assert_called_once_with("https://provider.invalid/mcp", "private-test-token", timeout=20)
            emitted = output.getvalue()
        self.assertNotIn("private-test-token", emitted)
        self.assertEqual("xiyou_keyword_metrics", json.loads(emitted.splitlines()[-1])["report_scope"])


class RestrictedTransportTests(unittest.TestCase):
    def transport(self):
        return RestrictedTransport("https://test-project.supabase.co", "fake-server-key", confirm_live=True)

    def test_explicit_live_gate_precedes_any_env_read(self):
        with patch("worker.runtime.production.os.environ") as env:
            with self.assertRaisesRegex(RuntimeFailure, "explicit confirmation"):
                RestrictedTransport.from_env()
            env.get.assert_not_called()

    def test_origin_and_header_injection_rejected(self):
        for origin in ("http://test.supabase.co", "https://test.supabase.co.evil.com", "https://test.supabase.co/path",
                       "https://user@test.supabase.co", "https://127.0.0.1", "https://test.supabase.co?x", "https://test.supabase.co\n"):
            with self.subTest(origin=origin), self.assertRaises(RuntimeFailure):
                RestrictedTransport(origin, "fake-key", confirm_live=True)
        with self.assertRaises(RuntimeFailure):
            RestrictedTransport("https://test.supabase.co", "key\r\nX: leak", confirm_live=True)

    def test_only_worker_paths_methods_and_headers_are_allowed(self):
        transport = self.transport()
        with patch("urllib.request.build_opener") as opener:
            for method, path, headers in (("GET", RPC, {}), ("POST", "/rest/v1/tasks", JSON_HEADERS),
                                          ("GET", "https://evil.com", {}), ("POST", RPC, {"Authorization": "evil"}),
                                          ("GET", f"/storage/v1/object/public/reports/{TASK}/{RUN}/report-{'a'*48}.json", {})):
                with self.subTest(path=path), self.assertRaises(RuntimeFailure):
                    transport.request(method, path, body=b"{}" if method == "POST" else None, headers=headers)
            opener.assert_not_called()

    def test_http_is_single_attempt_bounded_and_has_worker_credentials(self):
        transport = self.transport()
        response = io.BytesIO(b"null")
        response.status, response.headers = 200, {"Content-Length": "4"}
        opener = Mock()
        opener.open.return_value = response
        with patch("urllib.request.build_opener", return_value=opener) as build:
            self.assertEqual(b"null", transport.request("POST", RPC, body=b"{}", headers=JSON_HEADERS))
        opener.open.assert_called_once()
        request = opener.open.call_args.args[0]
        self.assertEqual("POST", request.get_method())
        self.assertEqual("Bearer fake-server-key", request.get_header("Authorization"))
        self.assertEqual("public", request.get_header("Content-profile"))
        self.assertEqual(20, opener.open.call_args.kwargs["timeout"])
        self.assertEqual({}, build.call_args.args[0].proxies)
        self.assertIsInstance(build.call_args.args[1], _NoRedirect)

    def test_no_redirect_no_retry_and_no_raw_error(self):
        transport = self.transport()
        self.assertIsNone(_NoRedirect().redirect_request(None, None, 302, "", {}, "https://evil.com"))
        for code in (301, 302, 307, 308, 429, 500):
            opener = Mock()
            opener.open.side_effect = urllib.error.HTTPError("https://test-project.supabase.co", code,
                                                            "SERVER-SECRET", {}, io.BytesIO(b"SERVER-SECRET"))
            with patch("urllib.request.build_opener", return_value=opener):
                with self.assertRaises(RuntimeFailure) as raised:
                    transport.request("POST", RPC, body=b"{}", headers=JSON_HEADERS)
            self.assertNotIn("SERVER-SECRET", str(raised.exception))
            opener.open.assert_called_once()

    def test_stream_bound_and_content_length_mismatch(self):
        for raw, headers, expected in ((b"123456", {}, "RESPONSE_TOO_LARGE"),
                                       (b"12", {"Content-Length": "4"}, "TRANSPORT_FAILED"),
                                       (b"12", {"Content-Length": "500"}, "RESPONSE_TOO_LARGE")):
            response = io.BytesIO(raw)
            response.status, response.headers = 200, headers
            opener = Mock()
            opener.open.return_value = response
            with patch("urllib.request.build_opener", return_value=opener), self.assertRaises(RuntimeFailure) as raised:
                self.transport().request("POST", RPC, body=b"{}", headers=JSON_HEADERS, max_response_bytes=4)
            self.assertEqual(expected, raised.exception.code)


if __name__ == "__main__":
    unittest.main()
