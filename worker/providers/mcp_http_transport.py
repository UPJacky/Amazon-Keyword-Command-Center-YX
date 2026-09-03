"""Single-attempt MCP Streamable HTTP transport.

The transport is deliberately small and opt-in.  It reads no environment
variables itself, never logs headers or response bodies, and returns only an
HTTP status for error responses so the provider retry contract can account
for 429/5xx without persisting remote error details.  A small allowlist of
safe response metadata is exposed through ``last_response_metadata`` for
auditing cost, retry and version behavior without returning credentials or
arbitrary server headers.
"""

from __future__ import annotations

import json
import math
from typing import Any, Callable, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


_MAX_RESPONSE_BYTES = 2 * 1024 * 1024
_MAX_RESPONSE_HEADER_VALUE = 256
_SAFE_RESPONSE_HEADERS = frozenset(
    {
        "content-type",
        "x-cost-credits",
        "retry-after",
        "x-ratelimit-limit",
        "x-ratelimit-remaining",
        "x-ratelimit-reset",
        "ratelimit-limit",
        "ratelimit-remaining",
        "ratelimit-reset",
        "x-api-version",
        "x-auth-version",
    }
)


def _valid_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value or any(ord(char) < 32 or 127 <= ord(char) <= 159 for char in value):
        raise ValueError(f"{label} must be a non-empty safe string")
    return value


def _safe_response_metadata(headers: Any) -> dict[str, str]:
    """Return bounded, allowlisted response headers only.

    Response metadata is provider-controlled input.  Invalid or oversized
    values are omitted instead of being persisted or allowed to break the
    transport.  In particular, Authorization and all unlisted headers never
    cross this boundary.
    """

    if headers is None or not hasattr(headers, "items"):
        return {}
    metadata: dict[str, str] = {}
    try:
        items = headers.items()
        for raw_name, raw_value in items:
            if not isinstance(raw_name, str) or not isinstance(raw_value, str):
                continue
            name = raw_name.lower()
            if name not in _SAFE_RESPONSE_HEADERS:
                continue
            if not raw_value or len(raw_value) > _MAX_RESPONSE_HEADER_VALUE:
                continue
            if any(ord(char) < 32 or 127 <= ord(char) <= 159 for char in raw_value):
                continue
            metadata[name] = raw_value
    except (AttributeError, TypeError, ValueError):
        return {}
    return metadata


class McpHttpTransport:
    """MCP HTTP transport implementing the provider ``call`` protocol."""

    def __init__(
        self,
        endpoint: str,
        token: str,
        *,
        timeout: float = 20.0,
        opener: Callable[..., Any] | None = None,
    ) -> None:
        endpoint = _valid_text(endpoint, "endpoint")
        token = _valid_text(token, "token")
        if any(char.isspace() for char in token):
            raise ValueError("token must not contain whitespace")
        parts = urlsplit(endpoint)
        if parts.scheme != "https" or not parts.hostname or parts.username or parts.password or parts.query or parts.fragment:
            raise ValueError("endpoint must be an HTTPS URL without credentials, query, or fragment")
        try:
            port = parts.port
        except ValueError as exc:
            raise ValueError("endpoint has an invalid port") from exc
        if port is not None and not 1 <= port <= 65535:
            raise ValueError("endpoint has an invalid port")
        if not isinstance(timeout, (int, float)) or isinstance(timeout, bool) or not math.isfinite(timeout) or timeout <= 0 or timeout > 60:
            raise ValueError("timeout must be finite and between 0 and 60 seconds")
        self._endpoint = endpoint
        self._token = token
        self._timeout = float(timeout)
        self._opener = opener or urlopen
        self._request_id = 0
        self._last_response_metadata: dict[str, str] = {}

    def __repr__(self) -> str:
        return f"McpHttpTransport(endpoint={self._endpoint!r}, timeout={self._timeout!r})"

    @property
    def last_response_metadata(self) -> dict[str, str]:
        """Return a copy of the latest allowlisted response metadata."""

        return self._last_response_metadata.copy()

    def call(self, tool_name: str, arguments: Mapping[str, Any]) -> Any:
        if not isinstance(tool_name, str) or not tool_name:
            raise ValueError("tool_name must be a non-empty string")
        if not isinstance(arguments, Mapping):
            raise ValueError("arguments must be an object")
        self._last_response_metadata = {}
        self._request_id += 1
        if tool_name == "jsonrpc":
            payload = dict(arguments)
        else:
            payload = {
                "jsonrpc": "2.0",
                "id": self._request_id,
                "method": "tools/call",
                "params": {"name": tool_name, "arguments": dict(arguments)},
            }
        try:
            body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        except (TypeError, ValueError) as exc:
            raise ValueError("arguments must be JSON serializable") from exc
        request = Request(
            self._endpoint,
            data=body,
            method="POST",
            headers={
                "Accept": "application/json, text/event-stream",
                "Authorization": f"Bearer {self._token}",
                "Content-Type": "application/json",
            },
        )
        try:
            with self._opener(request, timeout=self._timeout) as response:
                raw = response.read(_MAX_RESPONSE_BYTES + 1)
                if len(raw) > _MAX_RESPONSE_BYTES:
                    raise RuntimeError("MCP response exceeded the size limit")
                self._last_response_metadata = _safe_response_metadata(response.headers)
                return self._decode(raw, response.headers.get("Content-Type", ""))
        except HTTPError as exc:
            self._last_response_metadata = _safe_response_metadata(getattr(exc, "headers", None))
            status = getattr(exc, "code", None)
            if isinstance(status, int) and 100 <= status <= 599:
                return {"status": status}
            raise RuntimeError("MCP request failed") from None
        except (URLError, TimeoutError, OSError) as exc:
            raise RuntimeError("MCP request failed") from None

    @staticmethod
    def _decode(raw: bytes, content_type: str) -> Any:
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError("MCP response was not valid UTF-8") from exc
        if "text/event-stream" in content_type.lower():
            data = [line[5:].lstrip() for line in text.splitlines() if line.startswith("data:")]
            if not data:
                raise ValueError("MCP event stream contained no data")
            text = "\n".join(data)
        try:
            return json.loads(text)
        except (TypeError, ValueError) as exc:
            raise ValueError("MCP response was not valid JSON") from exc
