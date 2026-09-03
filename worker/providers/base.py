"""Provider-neutral cost, cache and usage contracts."""

from __future__ import annotations

import hashlib
import json
import math
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Protocol


class ProviderTransport(Protocol):
    def call(self, tool_name: str, arguments: Mapping[str, Any]) -> Any: ...


@dataclass(frozen=True)
class RetryPolicy:
    max_retries: int = 2
    backoff_seconds: tuple[int, ...] = (1, 2)
    retryable_statuses: tuple[int, ...] = (429, 500, 502, 503, 504)

    def __post_init__(self) -> None:
        if not isinstance(self.max_retries, int) or isinstance(self.max_retries, bool) or self.max_retries < 0:
            raise ValueError("max_retries must be a non-negative integer")
        if any(not isinstance(delay, (int, float)) or isinstance(delay, bool) or not math.isfinite(delay) or delay < 0 for delay in self.backoff_seconds):
            raise ValueError("backoff_seconds must contain finite non-negative numbers")
        if any(not isinstance(status, int) or isinstance(status, bool) or status < 100 or status > 599 for status in self.retryable_statuses):
            raise ValueError("retryable_statuses must contain HTTP status codes")


def retry_delay(transport: ProviderTransport, fallback: float, *, max_delay: float = 60.0) -> float:
    """Return a safe server-requested delay, falling back when unavailable.

    Transports may expose an allowlisted ``last_response_metadata`` mapping.
    Only a finite, non-negative numeric Retry-After value is accepted and it is
    capped so provider metadata cannot create an unbounded worker sleep.
    """
    metadata = getattr(transport, "last_response_metadata", None)
    if isinstance(metadata, Mapping):
        value = next((raw for key, raw in metadata.items() if str(key).lower() == "retry-after"), None)
        try:
            requested = float(value)
        except (TypeError, ValueError):
            requested = None
        if requested is not None and math.isfinite(requested) and requested >= 0:
            return min(requested, max_delay)
    return fallback


@dataclass
class UsageLog:
    requested_keywords: int = 0
    estimated_calls: int = 0
    cache_hits: int = 0
    actual_calls: int = 0
    rate_limited: int = 0
    failures: int = 0

    def to_dict(self) -> dict[str, int]:
        return self.__dict__.copy()


@dataclass(frozen=True)
class ProviderSnapshot:
    provider: str
    snapshot_version: str
    records: tuple[dict[str, Any], ...]
    missing_fields: tuple[str, ...] = ()


class ProviderContract:
    """Base contract; concrete providers must inject transport explicitly."""

    provider_name = "unconfigured"

    def __init__(self, transport: ProviderTransport | None = None, retry_policy: RetryPolicy | None = None, sleep_fn: Callable[[float], None] = time.sleep):
        self.transport = transport
        self.retry_policy = retry_policy or RetryPolicy()
        self.usage = UsageLog()
        self.sleep_fn = sleep_fn

    def estimate(self, keywords: list[str]) -> int:
        self.usage.requested_keywords = len(keywords)
        self.usage.estimated_calls = len(keywords)
        return self.usage.estimated_calls

    def cache_key(self, keyword: str, asin: str, marketplace: str) -> str:
        raw = json.dumps({"provider": self.provider_name, "keyword": keyword, "asin": asin, "marketplace": marketplace}, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def fetch(self, tool_name: str, arguments: Mapping[str, Any]) -> Any:
        if self.transport is None:
            self.usage.failures += 1
            raise RuntimeError("Provider transport is not configured; no paid call was made")
        attempts = self.retry_policy.max_retries + 1
        for attempt in range(attempts):
            self.usage.actual_calls += 1
            try:
                response = self.transport.call(tool_name, arguments)
            except Exception as exc:
                status = getattr(exc, "status_code", None)
                if status == 429:
                    self.usage.rate_limited += 1
                if status not in self.retry_policy.retryable_statuses or attempt == attempts - 1:
                    self.usage.failures += 1
                    raise
                self._backoff(attempt, status)
                continue
            status = response.get("status") if isinstance(response, Mapping) else None
            if status in self.retry_policy.retryable_statuses:
                if status == 429:
                    self.usage.rate_limited += 1
                if attempt == attempts - 1:
                    self.usage.failures += 1
                    raise RuntimeError(f"Provider request failed after retries: status={status}")
                self._backoff(attempt, status)
                continue
            return response
        raise RuntimeError("Provider request failed")

    def _backoff(self, attempt: int, status: int | None) -> None:
        fallback = self.retry_policy.backoff_seconds[min(attempt, len(self.retry_policy.backoff_seconds) - 1)] if self.retry_policy.backoff_seconds else 0
        delay = retry_delay(self.transport, fallback)  # type: ignore[arg-type]
        self.sleep_fn(delay)

    def normalize(self, raw: Any) -> dict[str, Any]:
        if not isinstance(raw, dict):
            raise ValueError("Provider response must be an object")
        return raw

    def snapshot(self, records: list[dict[str, Any]], missing_fields: list[str] | None = None) -> ProviderSnapshot:
        payload = json.dumps(records, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        version = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
        return ProviderSnapshot(self.provider_name, f"snapshot-{version}", tuple(records), tuple(missing_fields or []))
