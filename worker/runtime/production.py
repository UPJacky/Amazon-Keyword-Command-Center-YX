"""Supabase lease queue -> existing local pipeline -> verified private bundle.

No SDK, implicit credentials, redirects or transport retries. Network access
requires an injected transport or RestrictedTransport.from_env(confirm_live=True).
"""

from __future__ import annotations

import gc
import hashlib
import json
import math
import os
import re
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Mapping, Protocol
from uuid import UUID

from worker.config.config_merge import config_version, effective_config
from worker.pipeline.task_runner import ProviderEnricher, run_task
from worker.providers.config_validation import validate_config
from worker.rule_engine.engine import load_default_config

MAX_INPUT_BYTES = 10 * 1024 * 1024
MAX_REPORT_BYTES = 16 * 1024 * 1024
MAX_RPC_BYTES = 1024 * 1024
_UUID = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
_REPORT = r"report-[0-9a-f]{48}\.json"
_MODULE_ARTIFACTS = (
    "rank-benchmark.json", "negative-keywords.json", "competitors.json",
    "listing-diagnostics.json", "optimization-plan.json",
)
_RPC_NAMES = {"kwcc_claim_run", "kwcc_heartbeat_run", "kwcc_finish_run"}
_STAGE_TEMPLATES = {
    "new": "new_product_growth", "growth": "balanced_growth",
    "stable": "stable_profit", "clearance": "clearance",
    "seasonal_restart": "seasonal_restart",
}
_MESSAGES = {
    "LIVE_DISABLED": "Live transport requires explicit confirmation.",
    "SETTINGS_INVALID": "Worker settings are missing or invalid.",
    "REQUEST_INVALID": "Request is outside the worker transport contract.",
    "TRANSPORT_FAILED": "Upstream request failed; no retry was attempted.",
    "RESPONSE_TOO_LARGE": "Response exceeded the allowed byte limit.",
    "RPC_INVALID": "Queue RPC returned an invalid contract.",
    "INPUT_INVALID": "Task input identity, path, size or hash is invalid.",
    "INPUT_HASH_MISMATCH": "Downloaded input does not match the task SHA-256.",
    "INPUT_SIZE_MISMATCH": "Downloaded input does not match the declared size.",
    "INPUT_DOWNLOAD_FAILED": "Input download failed; no retry was attempted.",
    "CONFIG_INVALID": "Effective strategy configuration is invalid.",
    "RECONCILIATION_FAILED": "Input reconciliation failed before report generation.",
    "COMPETITOR_PROFILE_INVALID": "Injected competitor metadata is invalid.",
    "PROVIDER_ENRICHMENT_FAILED": "Injected Provider enrichment failed validation.",
    "REPORT_GENERATION_FAILED": "Local report generation failed.",
    "REPORT_UPLOAD_FAILED": "Private report upload or readback failed.",
    "PIPELINE_FAILED": "Local pipeline did not produce a completed report.",
    "REPORT_INVALID": "Local report artifacts failed bundle validation.",
    "REPORT_HASH_MISMATCH": "Private report readback does not match the uploaded bundle.",
    "LEASE_LOST": "Lease ownership could not be confirmed; completion was withheld.",
    "STOP_REQUESTED": "Worker shutdown requested; lease will expire for recovery.",
    "WORKER_FAILED": "Worker failed; upstream exception details were withheld.",
}
_FAILURE_STAGES = {
    "INPUT_INVALID": "ingestion", "INPUT_HASH_MISMATCH": "ingestion",
    "INPUT_SIZE_MISMATCH": "ingestion", "INPUT_DOWNLOAD_FAILED": "ingestion",
    "RECONCILIATION_FAILED": "reconciliation", "CONFIG_INVALID": "config",
    "COMPETITOR_PROFILE_INVALID": "competitors", "PROVIDER_ENRICHMENT_FAILED": "provider",
    "REPORT_GENERATION_FAILED": "report", "REPORT_UPLOAD_FAILED": "storage",
    "UNEXPECTED_TASK_ERROR": "worker",
}


class RuntimeFailure(Exception):
    """Only fixed public messages cross the worker boundary."""

    def __init__(self, code: str):
        self.code = code if code in _MESSAGES else "WORKER_FAILED"
        super().__init__(_MESSAGES[self.code])

    def record(self) -> dict[str, Any]:
        return {"code": self.code, "message": str(self), "stage": _FAILURE_STAGES.get(self.code, "worker"), "retryable": False}

    def rpc_record(self) -> dict[str, Any]:
        """005 accepts exactly three allowlisted fields, never an error message."""
        mapped = {"RESPONSE_TOO_LARGE": "INPUT_INVALID", "REPORT_HASH_MISMATCH": "REPORT_UPLOAD_FAILED",
                  "REPORT_INVALID": "REPORT_GENERATION_FAILED", "PIPELINE_FAILED": "UNEXPECTED_TASK_ERROR"}
        code = self.code if self.code in _FAILURE_STAGES else mapped.get(self.code, "UNEXPECTED_TASK_ERROR")
        return {"code": code, "stage": _FAILURE_STAGES[code], "retryable": False}


class Transport(Protocol):
    def request(self, method: str, path: str, *, body: bytes | None = None,
                headers: Mapping[str, str] | None = None,
                max_response_bytes: int = MAX_RPC_BYTES) -> bytes: ...


def _encode(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _decode(raw: bytes, code: str) -> Any:
    def reject_constant(_value):
        raise ValueError("nonfinite JSON")
    try:
        return json.loads(raw, parse_constant=reject_constant)
    except Exception:
        raise RuntimeFailure(code) from None


def _module_states(modules: Mapping[str, Any], report_scope: str) -> dict[str, dict[str, Any]]:
    """Describe availability without upgrading legacy artifacts to complete."""
    states: dict[str, dict[str, Any]] = {
        "master-table.json": {
            "status": "partial",
            "reason": "advertising_only" if report_scope == "ad_only" else "full_report_not_verified",
        }
    }
    for name in _MODULE_ARTIFACTS:
        artifact = modules.get(name)
        if artifact is None:
            states[name] = {"status": "not_generated", "reason": "artifact_not_generated"}
            continue
        declared = artifact.get("module_status") if isinstance(artifact, Mapping) else None
        if isinstance(declared, Mapping) and declared.get("status") in {"ready", "partial", "failed"}:
            reason = declared.get("reason")
            states[name] = {"status": declared["status"], "reason": reason if isinstance(reason, str) and reason else "module_declared_status"}
        else:
            states[name] = {"status": "partial", "reason": "legacy_artifact_without_status"}
    return states


def _uuid(value: Any, code: str = "INPUT_INVALID") -> str:
    if not isinstance(value, str) or not re.fullmatch(_UUID, value) or UUID(value).int == 0:
        raise RuntimeFailure(code)
    return value


def _positive(value: Any) -> bool:
    return type(value) in (int, float) and math.isfinite(value) and value > 0


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class RestrictedTransport:
    """HTTPS to one Supabase origin, allowlisted methods/paths, one attempt.

    Credentials are never accepted from task payloads or files. A caller that
    constructs this object explicitly is responsible for server-side env setup.
    """

    def __init__(self, base_url: str, service_key: str, *, confirm_live: bool = False,
                 timeout: float = 20):
        if confirm_live is not True:
            raise RuntimeFailure("LIVE_DISABLED")
        if (not isinstance(base_url, str)
                or not re.fullmatch(r"https://[a-z0-9][a-z0-9-]*\.supabase\.co/?", base_url)
                or not isinstance(service_key, str) or not service_key
                or any(ord(c) < 33 or ord(c) > 126 for c in service_key)
                or not _positive(timeout) or timeout > 60):
            raise RuntimeFailure("SETTINGS_INVALID")
        self._base_url = base_url.rstrip("/")
        self._service_key = service_key
        self.timeout = timeout
        self.network_calls = 0

    @classmethod
    def from_env(cls, *, confirm_live: bool = False, timeout: float = 20):
        if confirm_live is not True:
            raise RuntimeFailure("LIVE_DISABLED")
        return cls(os.environ.get("SUPABASE_URL", ""),
                   os.environ.get("SUPABASE_SERVICE_ROLE_KEY", ""),
                   confirm_live=True, timeout=timeout)

    def request(self, method, path, *, body=None, headers=None, max_response_bytes=MAX_RPC_BYTES):
        rpc = isinstance(path, str) and path in {f"/rest/v1/rpc/{name}" for name in _RPC_NAMES}
        input_get = isinstance(path, str) and re.fullmatch(
            rf"/storage/v1/object/authenticated/inputs/{_UUID}/{_UUID}/{_UUID}/input\.(xlsx|csv)", path)
        report_get = isinstance(path, str) and re.fullmatch(
            rf"/storage/v1/object/authenticated/reports/{_UUID}/{_UUID}/{_REPORT}", path)
        report_post = isinstance(path, str) and re.fullmatch(
            rf"/storage/v1/object/reports/{_UUID}/{_UUID}/{_REPORT}", path)
        expected_headers = {"Content-Type": "application/json"}
        if report_post:
            expected_headers["x-upsert"] = "false"
        if (not ((rpc and method == "POST") or ((input_get or report_get) and method == "GET")
                 or (report_post and method == "POST"))
                or dict(headers or {}) != (expected_headers if method == "POST" else {})
                or (method == "POST" and not isinstance(body, bytes))
                or (method == "GET" and body is not None)
                or type(max_response_bytes) is not int or not 0 < max_response_bytes <= MAX_REPORT_BYTES):
            raise RuntimeFailure("REQUEST_INVALID")
        auth = {"apikey": self._service_key, "Authorization": f"Bearer {self._service_key}",
                "Accept": "application/json", "Accept-Encoding": "identity", **dict(headers or {})}
        if rpc:
            auth.update({"Accept-Profile": "public", "Content-Profile": "public"})
        try:
            request = urllib.request.Request(self._base_url + path, data=body, headers=auth, method=method)
            # No environment proxies; each call gets an independent opener for heartbeat concurrency.
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())
            self.network_calls += 1
            deadline = time.monotonic() + self.timeout
            with opener.open(request, timeout=self.timeout) as response:
                if not 200 <= response.status < 300:
                    raise RuntimeFailure("TRANSPORT_FAILED")
                length = response.headers.get("Content-Length")
                if length is not None and (not length.isdecimal() or int(length) > max_response_bytes):
                    raise RuntimeFailure("RESPONSE_TOO_LARGE")
                chunks, total = [], 0
                while True:
                    if time.monotonic() >= deadline:
                        raise RuntimeFailure("TRANSPORT_FAILED")
                    chunk = response.read1(min(65536, max_response_bytes + 1 - total))
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > max_response_bytes:
                        raise RuntimeFailure("RESPONSE_TOO_LARGE")
                    chunks.append(chunk)
                if length is not None and total != int(length):
                    raise RuntimeFailure("TRANSPORT_FAILED")
                return b"".join(chunks)
        except RuntimeFailure:
            raise
        except urllib.error.HTTPError as exc:
            exc.close()
            raise RuntimeFailure("TRANSPORT_FAILED") from None
        except Exception:
            raise RuntimeFailure("TRANSPORT_FAILED") from None


def build_effective_config(task: Mapping[str, Any], strategy: Any) -> dict[str, Any]:
    """Stable base -> existing stage template -> selected strategy -> task override."""
    try:
        stage = task["product_stage"]
        template_name = _STAGE_TEMPLATES[stage]
        templates = _decode((Path(__file__).resolve().parents[2] / "rules/strategy_templates.json").read_bytes(), "CONFIG_INVALID")
        override = task.get("task_config_override")
        strategy = {} if strategy is None else strategy
        override = {} if override is None else override
        if not isinstance(strategy, dict) or not isinstance(override, dict):
            raise ValueError()
        for layer in (strategy, override):
            if "product_stage" in layer and layer["product_stage"] != stage:
                raise ValueError()
        result = effective_config({"global": load_default_config(), "stage": templates["templates"][template_name],
                                   "asin": strategy, "task": override})
        result.pop("config_version", None)
        _encode(result)
        if validate_config(result):
            raise ValueError()
        result["config_version"] = config_version(result)
        return result
    except Exception:
        raise RuntimeFailure("CONFIG_INVALID") from None


class _Lease:
    def __init__(self, worker, run, claimed_at):
        self.worker, self.run = worker, run
        self.deadline = claimed_at + worker.lease_seconds
        self.lost = threading.Event()
        self.done = threading.Event()
        self.lock = threading.RLock()
        self.thread = threading.Thread(target=self._loop, name="kwcc-lease-heartbeat", daemon=True)

    def check(self):
        if self.worker.stop_event.is_set():
            raise RuntimeFailure("STOP_REQUESTED")
        if self.lost.is_set() or time.monotonic() >= self.deadline:
            self.lost.set()
            raise RuntimeFailure("LEASE_LOST")

    def renew(self):
        with self.lock:
            if self.done.is_set():
                return
            self.check()
            started = time.monotonic()
            try:
                ok = self.worker._rpc("kwcc_heartbeat_run", {
                    "p_run_id": self.run["run_id"], "p_lease_token": self.run["lease_token"],
                    "p_lease_seconds": self.worker.lease_seconds})
                self.check()
                if ok is not True:
                    raise RuntimeFailure("LEASE_LOST")
                self.deadline = started + self.worker.lease_seconds
            except Exception:
                self.lost.set()
                raise RuntimeFailure("LEASE_LOST") from None

    def _loop(self):
        while not self.done.wait(self.worker.heartbeat_interval):
            try:
                self.renew()
            except RuntimeFailure:
                return

    def __enter__(self):
        self.renew()
        self.thread.start()
        return self

    def __exit__(self, *_args):
        self.done.set()
        self.thread.join(timeout=1)


class ProductionWorker:
    def __init__(self, transport: Transport | None = None, *, worker_id: str = "kwcc-worker",
                 lease_seconds: int = 300, heartbeat_interval: float | None = None,
                 provider_enricher: ProviderEnricher | None = None,
                 provider_factory=None,
                 competitor_profile: Mapping[str, Any] | None = None,
                 stop_event: threading.Event | None = None):
        interval = lease_seconds / 3 if heartbeat_interval is None and type(lease_seconds) is int else heartbeat_interval
        if (not isinstance(worker_id, str) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", worker_id)
                or type(lease_seconds) is not int or not 3 <= lease_seconds <= 3600
                or not _positive(interval) or interval > lease_seconds / 3
                or (provider_enricher is not None and not callable(provider_enricher))
                or (provider_factory is not None and not callable(provider_factory))
                or (provider_factory is not None and provider_enricher is not None)):
            raise RuntimeFailure("SETTINGS_INVALID")
        self.transport, self.worker_id = transport, worker_id
        self.lease_seconds, self.heartbeat_interval = lease_seconds, interval
        self.provider_enricher, self.competitor_profile = provider_enricher, competitor_profile
        self.provider_factory = provider_factory
        self.stop_event = stop_event if stop_event is not None else threading.Event()

    def _request(self, method, path, *, body=None, headers=None, limit=MAX_RPC_BYTES):
        if self.transport is None:
            raise RuntimeFailure("LIVE_DISABLED")
        try:
            raw = self.transport.request(method, path, body=body, headers=headers, max_response_bytes=limit)
            if not isinstance(raw, bytes):
                raise RuntimeFailure("TRANSPORT_FAILED")
            if len(raw) > limit:
                raise RuntimeFailure("RESPONSE_TOO_LARGE")
            return raw
        except RuntimeFailure:
            raise
        except Exception:
            raise RuntimeFailure("TRANSPORT_FAILED") from None

    def _rpc(self, name, payload):
        return _decode(self._request("POST", f"/rest/v1/rpc/{name}", body=_encode(payload),
                                     headers={"Content-Type": "application/json"}), "RPC_INVALID")

    def _input(self, task):
        if not isinstance(task, dict):
            raise RuntimeFailure("INPUT_INVALID")
        ids = [_uuid(task.get(name)) for name in ("store_id", "created_by", "task_id")]
        path = task.get("input_file_path")
        prefix = "/".join(ids) + "/input."
        # Queue stores the object key, without bucket prefix, URLs or encoding.
        if path not in (prefix + "xlsx", prefix + "csv"):
            raise RuntimeFailure("INPUT_INVALID")
        digest = task.get("input_file_hash")
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", digest):
            raise RuntimeFailure("INPUT_INVALID")
        if not isinstance(task.get("self_asin"), str) or not re.fullmatch(r"[A-Z0-9]{10}", task["self_asin"]):
            raise RuntimeFailure("INPUT_INVALID")
        for field in ("input_size", "input_file_size", "input_file_size_bytes"):
            size = task.get(field)
            if size is not None and (type(size) is not int or not 0 < size <= MAX_INPUT_BYTES):
                raise RuntimeFailure("INPUT_INVALID")
        try:
            raw = self._request("GET", f"/storage/v1/object/authenticated/inputs/{path}", limit=MAX_INPUT_BYTES)
        except RuntimeFailure as exc:
            if exc.code == "RESPONSE_TOO_LARGE":
                raise
            raise RuntimeFailure("INPUT_DOWNLOAD_FAILED") from None
        if not raw:
            raise RuntimeFailure("INPUT_INVALID")
        for field in ("input_size", "input_file_size", "input_file_size_bytes"):
            if task.get(field) is not None and len(raw) != task[field]:
                raise RuntimeFailure("INPUT_SIZE_MISMATCH")
        if hashlib.sha256(raw).hexdigest() != digest.lower():
            raise RuntimeFailure("INPUT_HASH_MISMATCH")
        return raw, Path(path).suffix

    def _bundle(self, result, storage, task, run, provider_state):
        try:
            root = storage / task["task_id"] / run["run_id"]
            path = Path(result.report_path)
            if path.parent != root or not re.fullmatch(_REPORT, path.name) or path.is_symlink():
                raise ValueError()
            master = _decode(path.read_bytes(), "REPORT_INVALID")
            if (not isinstance(master, dict) or master.get("reconciliation", {}).get("passed") is not True
                    or master.get("input_sha256") != task["input_file_hash"].lower()):
                raise ValueError()
            modules = {}
            # Keep the registry identical to _MODULE_ARTIFACTS and the frontend
            # allowlist. Listing diagnostics used to be generated locally but
            # silently omitted from the production bundle.
            for name in ("rank-benchmark", "negative-keywords", "competitors", "listing-diagnostics", "optimization-plan"):
                artifact = root / f"{name}.json"
                if artifact.exists():
                    if artifact.is_symlink():
                        raise ValueError()
                    modules[f"{name}.json"] = _decode(artifact.read_bytes(), "REPORT_INVALID")
                elif name != "competitors":
                    raise ValueError()
            if (master.get("schema_version") != "report-0.2" or not isinstance(master.get("rows"), list)
                    or any(not isinstance(row, dict) for row in master["rows"])):
                raise ValueError()
            metadata = {field: task[field] for field in ("self_asin", "store_id", "product_stage", "marketplace")
                        if isinstance(task.get(field), str) and task[field].strip()}
            report_scope = "ad_only" if self.provider_enricher is None and self.provider_factory is None else "injected_provider_data"
            bundle = {**master, **metadata, "task_id": task["task_id"], "run_id": run["run_id"],
                      "modules": modules, "module_states": _module_states(modules, report_scope),
                      "provider_evidence": provider_state, "report_scope": report_scope,
                      "full_report_complete": False}
            raw = _encode(bundle)
            if len(raw) > MAX_REPORT_BYTES:
                raise ValueError()
            return f"{task['task_id']}/{run['run_id']}/{path.name}", raw, master
        except Exception:
            raise RuntimeFailure("REPORT_INVALID") from None

    def run_once(self) -> dict[str, Any]:
        if self.transport is None:
            return {"status": "disabled", "network_calls": 0}
        if self.stop_event.is_set():
            return {"status": "stopped"}
        try:
            claimed_at = time.monotonic()
            claim = self._rpc("kwcc_claim_run", {"p_worker_id": self.worker_id, "p_lease_seconds": self.lease_seconds})
            if claim is None:
                return {"status": "idle"}
            if not isinstance(claim, dict) or not isinstance(claim.get("run"), dict):
                raise RuntimeFailure("RPC_INVALID")
            run = claim["run"]
            _uuid(run.get("run_id"), "RPC_INVALID")
            _uuid(run.get("lease_token"), "RPC_INVALID")
            lease = _Lease(self, run, claimed_at)
            with lease:
                return self._execute(claim, lease)
        except Exception as exc:
            safe = exc if isinstance(exc, RuntimeFailure) else RuntimeFailure("WORKER_FAILED")
            return {"status": "error", "failure_reason": safe.record(), "pending": True}

    def _execute(self, claim, lease):
        run = claim["run"]
        attempted_finish = False

        def finish(status, *, report_path=None, master=None, reason=None):
            nonlocal attempted_finish
            with lease.lock:
                lease.renew()
                lease.check()
                payload = {"p_run_id": run["run_id"], "p_lease_token": run["lease_token"], "p_status": status,
                           "p_report_path": report_path, "p_failure_reason": reason}
                for field in ("rule_version", "config_version", "provider_snapshot_version"):
                    payload[f"p_{field}"] = (master or {}).get(field)
                # A timeout after POST is ambiguous: never send a second finish.
                attempted_finish = True
                accepted = self._rpc("kwcc_finish_run", payload)
                lease.check()
                if accepted is not True:
                    lease.lost.set()
                    raise RuntimeFailure("LEASE_LOST")
                lease.done.set()

        try:
            task = claim.get("task")
            if not isinstance(task, dict) or "config" not in claim:
                raise RuntimeFailure("RPC_INVALID")
            if run.get("task_id", task.get("task_id")) != task.get("task_id"):
                raise RuntimeFailure("INPUT_INVALID")
            if self.competitor_profile is not None and (
                    not isinstance(self.competitor_profile, Mapping)
                    or self.competitor_profile.get("self_asin") != task.get("self_asin")):
                raise RuntimeFailure("COMPETITOR_PROFILE_INVALID")
            cfg = build_effective_config(task, claim["config"])
            raw, extension = self._input(task)
            lease.check()
            enricher = self.provider_enricher
            if self.provider_factory is not None:
                # Only metadata is handed to the factory; never operational lease credentials.
                try:
                    enricher = self.provider_factory({key: task.get(key) for key in
                        ("task_id", "store_id", "self_asin", "product_stage", "marketplace")})
                    if not callable(enricher):
                        raise ValueError()
                except Exception:
                    raise RuntimeFailure("PROVIDER_ENRICHMENT_FAILED") from None
            with TemporaryDirectory(prefix="kwcc-production-") as directory:
                root = Path(directory)
                source, storage = root / f"input{extension}", root / "artifacts"
                source.write_bytes(raw)
                provider_state = {"status": "not_requested", "real_provider_verified": False}

                def enrich(parsed, config):
                    lease.check()
                    value = enricher(parsed, config)
                    lease.check()
                    provider_state["status"] = "injected_data" if isinstance(value, Mapping) and value.get("market_rows") else "no_market_data"
                    # Injection is evidence of data, not proof of live Provider provenance.
                    return value

                try:
                    result = run_task(source, storage, task["task_id"], run["run_id"], config=cfg,
                                      provider_enricher=enrich if enricher is not None else None,
                                      competitor_profile=self.competitor_profile,
                                      my_asin=task["self_asin"])
                finally:
                    # Existing parser leaves read-only workbook cycles for GC.
                    # Release those handles before TemporaryDirectory cleanup on Windows.
                    if extension == ".xlsx":
                        gc.collect()
                lease.check()
                if result.status != "completed":
                    code = result.failure_reason.get("code") if isinstance(result.failure_reason, dict) else None
                    raise RuntimeFailure(code if code in _FAILURE_STAGES and code in _MESSAGES else "PIPELINE_FAILED")
                report_path, bundle, master = self._bundle(result, storage, task, run, provider_state)
            # Cleanup must also succeed before publishing or committing completion.
            lease.check()
            try:
                self._request("POST", f"/storage/v1/object/reports/{report_path}", body=bundle,
                              headers={"Content-Type": "application/json", "x-upsert": "false"})
                lease.check()
                readback = self._request("GET", f"/storage/v1/object/authenticated/reports/{report_path}", limit=MAX_REPORT_BYTES)
            except RuntimeFailure as exc:
                if exc.code in ("LEASE_LOST", "STOP_REQUESTED"):
                    raise
                raise RuntimeFailure("REPORT_UPLOAD_FAILED") from None
            if hashlib.sha256(readback).digest() != hashlib.sha256(bundle).digest():
                raise RuntimeFailure("REPORT_HASH_MISMATCH")
            lease.check()
            finish("completed", report_path=report_path, master=master)
            return {"status": "completed", "task_id": task["task_id"], "run_id": run["run_id"],
                    "report_path": report_path, "report_sha256": hashlib.sha256(bundle).hexdigest(),
                    "report_scope": "ad_only" if enricher is None else "injected_provider_data",
                    "full_report_complete": False}
        except Exception as exc:
            safe = exc if isinstance(exc, RuntimeFailure) else RuntimeFailure("WORKER_FAILED")
            if attempted_finish:
                return {"status": "error", "failure_reason": safe.record(), "pending": True, "finish_attempted": True}
            try:
                lease.check()
                finish("failed", reason=safe.rpc_record())
            except RuntimeFailure as finish_error:
                return {"status": "error", "failure_reason": finish_error.record(), "pending": True,
                        "finish_attempted": attempted_finish}
            return {"status": "failed", "failure_reason": safe.record(), "pending": False}

    def run_loop(self, *, poll_interval: float = 1, max_cycles: int | None = None, on_cycle=None):
        if (not _positive(poll_interval) or (max_cycles is not None and
                (type(max_cycles) is not int or max_cycles < 1))):
            raise RuntimeFailure("SETTINGS_INVALID")
        stats = {"cycles": 0, "completed": 0, "failed": 0, "errors": 0, "idle": 0, "disabled": 0}
        while not self.stop_event.is_set() and (max_cycles is None or stats["cycles"] < max_cycles):
            result = self.run_once()
            stats["cycles"] += 1
            key = "errors" if result["status"] == "error" else result["status"]
            if key in stats:
                stats[key] += 1
            if on_cycle is not None:
                on_cycle(result)
            if max_cycles is not None and stats["cycles"] >= max_cycles:
                break
            self.stop_event.wait(poll_interval)
        stats["stopped"] = self.stop_event.is_set()
        if self.transport is None:
            stats["network_calls"] = 0
        elif isinstance(self.transport, RestrictedTransport):
            stats["network_calls"] = self.transport.network_calls
        return stats
