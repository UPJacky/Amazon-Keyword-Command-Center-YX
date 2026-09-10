"""Bounded native Sorftime MCP transport; query credentials stay private."""

import json
import math
from urllib.error import HTTPError
from urllib.parse import parse_qsl, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class SorftimeTransport:
    def __init__(self, endpoint, *, timeout=25, opener=None):
        try:
            parts = urlsplit(endpoint)
            query = parse_qsl(parts.query, keep_blank_values=True)
            valid = (parts.scheme == "https" and parts.hostname == "mcp.sorftime.com"
                     and not parts.username and not parts.password and not parts.fragment
                     and parts.port in (None, 443) and len(query) == 1
                     and query[0][0] == "key" and bool(query[0][1])
                     and not any(char.isspace() or ord(char) < 32 for char in endpoint))
        except (ValueError, TypeError, AttributeError):
            valid = False
        if not valid:
            raise ValueError("Invalid Sorftime endpoint configuration")
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or not 0 < timeout <= 60:
            raise ValueError("Invalid Sorftime timeout")
        self._endpoint = endpoint
        self._timeout = timeout
        self._open = opener or build_opener(_NoRedirect()).open
        self._request_id = 0

    def __repr__(self):
        return "SorftimeTransport(endpoint=<redacted>)"

    def call(self, tool_name, arguments):
        if not isinstance(tool_name, str) or not tool_name or not isinstance(arguments, dict):
            raise ValueError("Invalid Sorftime call")
        self._request_id += 1
        payload = ({"jsonrpc": "2.0", "id": self._request_id,
                    "method": "tools/list", "params": {}} if tool_name == "tools/list" else
                   {"jsonrpc": "2.0", "id": self._request_id, "method": "tools/call",
                    "params": {"name": tool_name, "arguments": arguments}})
        try:
            body = json.dumps(payload, allow_nan=False).encode("utf-8")
            request = Request(self._endpoint, data=body, method="POST", headers={
                "Accept": "application/json, text/event-stream", "Content-Type": "application/json"})
            with self._open(request, timeout=self._timeout) as response:
                raw = response.read(2 * 1024 * 1024 + 1)
                if len(raw) > 2 * 1024 * 1024:
                    raise ValueError("oversized response")
                text = raw.decode("utf-8-sig")
                if "text/event-stream" in response.headers.get("Content-Type", "").lower():
                    events = text.replace("\r\n", "\n").split("\n\n")
                    candidates = [json.loads("\n".join(line[5:].lstrip() for line in event.splitlines()
                                                       if line.startswith("data:")))
                                  for event in events if any(line.startswith("data:") for line in event.splitlines())]
                else:
                    candidates = [json.loads(text)]
                matches = [value for value in candidates if isinstance(value, dict)
                           and value.get("jsonrpc") == "2.0" and type(value.get("id")) is int
                           and value["id"] == payload["id"]]
                if len(matches) != 1 or "error" in matches[0] or "result" not in matches[0]:
                    raise ValueError("invalid RPC response")
                return matches[0]["result"]
        except HTTPError as exc:
            raise RuntimeError(f"Sorftime HTTP {exc.code}") from None
        except Exception:
            # urllib errors may contain the full credential-bearing URL.
            raise RuntimeError("Sorftime request or response failed") from None
