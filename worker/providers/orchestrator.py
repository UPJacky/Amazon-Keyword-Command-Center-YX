"""Opt-in, transport-neutral small samples with a shared hard call budget.

No transport, credentials, tool names, field mapping or monetary prices are
discovered here. Inject a *single-attempt* transport (no hidden SDK retries), a
validated normalizer and a request builder from the production composition root.
Reuse the orchestrator/budget across runs to retain its lifetime call ceiling.
Use the same CallBudget across instances for a shared in-process ceiling; this
is not a distributed budget. Cache namespaces must partition accounts/datasets
using non-secret identifiers, and versions must change with provider schemas or
normalization semantics. Arguments are JSON data, never credentials.
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Sequence

from worker.providers.base import ProviderTransport, RetryPolicy, retry_delay
from worker.providers.cache import ProviderCache


CACHE_KEY_VERSION = "provider-request-v1"


def _json(value: Any) -> str:
    # Reject lossy JSON coercion (integer keys, tuples, NaN, arbitrary objects).
    def check(item: Any) -> None:
        if type(item) is dict:
            if any(type(key) is not str for key in item):
                raise ValueError("JSON object keys must be strings")
            for child in item.values():
                check(child)
        elif type(item) is list:
            for child in item:
                check(child)
        elif item is not None and type(item) not in (str, int, float, bool):
            raise ValueError("Only JSON data is supported")

    check(value)
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _digest(value: Any) -> str:
    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()


def _nonnegative_int(value: Any) -> bool:
    return type(value) is int and value >= 0


def _usage() -> dict[str, int]:
    return dict(requested_requests=0, unique_requests=0, duplicates_suppressed=0,
                cache_hits=0, actual_calls=0, retries=0, rate_limited=0, failures=0)


@dataclass(frozen=True)
class ProviderRequest:
    tool_name: str
    arguments: Mapping[str, Any]


class ProviderBatchError(RuntimeError):
    """Safe machine-readable failure, without raw transport/normalizer details."""

    def __init__(self, code: str, usage: dict[str, int]):
        self.code = code
        self.usage = usage.copy()
        super().__init__(f"Provider batch failed: {code}")


class CallBudget:
    """Thread-safe lifetime ceiling on transport attempts, including failures.

    Reservations are never refunded: a transport exception cannot prove that
    the remote side did not receive a request. Share this object explicitly.
    """

    def __init__(self, max_calls: int):
        if not _nonnegative_int(max_calls):
            raise ValueError("max_calls must be an explicit non-negative integer")
        self._max_calls = max_calls
        self._used = 0
        self._lock = threading.Lock()

    @property
    def max_calls(self) -> int:
        return self._max_calls

    @property
    def used(self) -> int:
        with self._lock:
            return self._used

    def reserve(self) -> bool:
        with self._lock:
            if self._used >= self._max_calls:
                return False
            self._used += 1
            return True


class ProviderBatchOrchestrator:
    """Serialize runs on an instance; reuse successful normalized cache entries.

    ``run`` returns unique request results in first-seen order (duplicates do
    not duplicate market rows). ``refresh=True`` bypasses cache reads, still
    deduplicates the batch, and replaces only successful entries. A failed
    refresh does not delete the last good entry. Each normalizer returns one
    JSON object and must reject provider-specific application errors and invalid
    fields. Successful earlier items may be cached if a later item fails, but
    partial market rows are never returned as a successful batch.
    """

    def __init__(
        self, *, provider: str, provider_version: str, normalizer_version: str,
        cache_namespace: str, cache: ProviderCache,
        normalize: Callable[[Any], dict[str, Any]],
        transport: ProviderTransport | None = None, budget: CallBudget | None = None,
        enabled: bool = False, max_requests: int = 30,
        retry_policy: RetryPolicy | None = None,
        sleep_fn: Callable[[float], None] = time.sleep,
    ):
        identity = {
            "key_version": CACHE_KEY_VERSION, "provider": provider,
            "provider_version": provider_version,
            "normalizer_version": normalizer_version, "namespace": cache_namespace,
        }
        if any(type(value) is not str or not value.strip() for value in identity.values()):
            raise ValueError("Provider identity and versions must be non-empty strings")
        if type(enabled) is not bool or not _nonnegative_int(max_requests) or max_requests == 0:
            raise ValueError("enabled must be boolean and max_requests a positive integer")
        if not callable(normalize) or not callable(sleep_fn):
            raise ValueError("normalize and sleep_fn must be callable")
        if budget is not None and not isinstance(budget, CallBudget):
            raise ValueError("budget must be a CallBudget")
        if retry_policy is not None and not isinstance(retry_policy, RetryPolicy):
            raise ValueError("retry_policy must be a RetryPolicy")
        call = None if transport is None else getattr(transport, "call", None)
        if transport is not None and not callable(call):
            raise ValueError("transport must provide a single-attempt call method")
        self._identity = identity
        self._cache = cache
        self._normalize = normalize
        self._transport = transport
        self._call = call
        self._budget = budget
        self._enabled = enabled
        self._max_requests = max_requests
        self._retry = retry_policy or RetryPolicy()
        self._sleep = sleep_fn
        self._run_lock = threading.Lock()

    def _prepare(self, request: ProviderRequest) -> tuple[str, str]:
        if not isinstance(request, ProviderRequest):
            raise ValueError("Expected ProviderRequest")
        if type(request.tool_name) is not str or not request.tool_name.strip():
            raise ValueError("tool_name must be non-empty")
        if not isinstance(request.arguments, Mapping):
            raise ValueError("arguments must be an object")
        # Snapshot once: transport/caller mutation cannot change retries or key.
        payload = {"tool_name": request.tool_name, "arguments": dict(request.arguments)}
        serialized = _json(payload)
        return _digest({**self._identity, "request": payload}), serialized

    def cache_key(self, request: ProviderRequest) -> str:
        """Canonical complete request key; strings/list order retain semantics."""
        return self._prepare(request)[0]

    @staticmethod
    def _fail(code: str, usage: dict[str, int]) -> None:
        usage["failures"] += 1
        raise ProviderBatchError(code, usage) from None

    def _fetch(self, serialized: str, usage: dict[str, int]) -> Any:
        if self._call is None:
            self._fail("TRANSPORT_NOT_CONFIGURED", usage)
        if self._budget is None:
            self._fail("BUDGET_NOT_CONFIGURED", usage)
        for attempt in range(self._retry.max_retries + 1):
            payload = json.loads(serialized)
            if not self._budget.reserve():
                self._fail("BUDGET_EXHAUSTED", usage)
            usage["actual_calls"] += 1
            usage["retries"] += int(attempt > 0)
            failed = False
            try:
                response = self._call(payload["tool_name"], payload["arguments"])
            except Exception as exc:
                status = getattr(exc, "status_code", None)
                failed = True
            else:
                status = response.get("status") if isinstance(response, Mapping) else None
                if isinstance(response, Mapping) and (
                    response.get("error") is not None or response.get("isError") is True
                ):
                    failed = True
            if status is not None and (type(status) is not int or not 100 <= status <= 599):
                self._fail("INVALID_RESPONSE_STATUS", usage)
            if status == 429:
                usage["rate_limited"] += 1
            if status in self._retry.retryable_statuses:
                if attempt == self._retry.max_retries:
                    self._fail("RETRIES_EXHAUSTED", usage)
                # Avoid backoff once no calls remain. reserve() is still the
                # authoritative check after backoff if another batch races us.
                if self._budget.used >= self._budget.max_calls:
                    self._fail("BUDGET_EXHAUSTED", usage)
                delays = self._retry.backoff_seconds
                fallback = delays[min(attempt, len(delays) - 1)] if delays else 0
                self._sleep(retry_delay(self._transport, fallback))  # type: ignore[arg-type]
                continue
            if failed or (status is not None and not 200 <= status < 300):
                self._fail("TRANSPORT_FAILED", usage)
            return response
        self._fail("RETRIES_EXHAUSTED", usage)

    def run(self, requests: Sequence[ProviderRequest], *, refresh: bool = False) -> dict[str, Any]:
        """Return market_rows, provider_snapshot_version and per-run integer usage.

        No injected transport/budget means cache-only operation when enabled;
        misses fail closed. Explicitly disabled operation always fails closed.
        """
        usage = _usage()
        with self._run_lock:
            try:
                if not self._enabled:
                    self._fail("NOT_ENABLED", usage)
                if type(refresh) is not bool or not isinstance(requests, (list, tuple)):
                    self._fail("INVALID_BATCH", usage)
                usage["requested_requests"] = len(requests)
                # Bound the entire submitted small sample, including duplicates.
                if len(requests) > self._max_requests:
                    self._fail("SAMPLE_LIMIT_EXCEEDED", usage)
                unique = dict(self._prepare(request) for request in requests)
                usage["unique_requests"] = len(unique)
                usage["duplicates_suppressed"] = len(requests) - len(unique)
                rows = []
                for key, serialized in unique.items():
                    cached = None if refresh else self._cache.get(key)
                    if cached is not None:
                        if (cached.get("cache_key") != key
                                or cached.get("provider") != self._identity["provider"]
                                or type(cached.get("data")) is not dict
                                or cached.get("snapshot_version") != self._row_version(key, cached["data"])):
                            self._fail("INVALID_CACHE_ENTRY", usage)
                        row = json.loads(_json(cached["data"]))
                        usage["cache_hits"] += 1
                    else:
                        raw = self._fetch(serialized, usage)
                        row = self._normalize(raw)
                        if type(row) is not dict:
                            self._fail("INVALID_NORMALIZED_ROW", usage)
                        row = json.loads(_json(row))
                        self._cache.set(key, provider=self._identity["provider"],
                                        snapshot_version=self._row_version(key, row), data=row)
                    rows.append(row)
                version = "provider-batch-v1-" + _digest({
                    "identity": self._identity, "request_keys": list(unique), "rows": rows,
                })
                return {"market_rows": rows, "provider_snapshot_version": version, "usage": usage}
            except ProviderBatchError:
                raise
            except Exception:
                self._fail("INVALID_BATCH_OR_PROVIDER_DATA", usage)

    @staticmethod
    def _row_version(key: str, row: dict[str, Any]) -> str:
        return "provider-row-v1-" + _digest({"request_key": key, "row": row})

    def as_enricher(self, request_builder: Callable, *, refresh: bool = False) -> Callable:
        """Create ``provider_enricher(parsed, effective_config)`` for task_runner.

        The explicit builder supplies confirmed tool/argument semantics; this
        module never infers them from parsed data or changes decision rules.
        """
        if not callable(request_builder) or type(refresh) is not bool:
            raise ValueError("A callable request_builder and boolean refresh are required")

        def enrich(parsed: Any, effective_config: Any) -> dict[str, Any]:
            try:
                requests = request_builder(parsed, effective_config)
            except Exception:
                self._fail("REQUEST_BUILD_FAILED", _usage())
            return self.run(requests, refresh=refresh)

        return enrich
