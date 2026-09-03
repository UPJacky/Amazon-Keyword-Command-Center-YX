"""Explicit-injection Supabase HTTP transport.

No HTTP client is created automatically. Production wiring must inject a
request function after origin, RLS and secret handling are reviewed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import base64
import json
from typing import Any, Callable, Mapping
from urllib.parse import urlparse
import re


class HttpTransportNotConfigured(RuntimeError):
    pass


class PrivateReportError(RuntimeError):
    """A fixed, credential-free error; upstream bodies are never exposed."""


@dataclass(frozen=True)
class HttpResponse:
    """Required response envelope for read_report_content only.

    status_code is the actual HTTP status (redirects must not be followed).
    body is decoded JSON for Auth/REST and decoded JSON or UTF-8 bytes for
    Storage. Injected clients must not log credentials, follow redirects, retry
    with elevated credentials, or replace authenticated reads with signed URLs.
    Legacy metadata operations retain their existing passthrough response.
    """

    status_code: int
    body: Any = field(repr=False)


def _reject_elevated_key(value: str | None) -> None:
    # This is rejection only, never JWT verification. Auth verifies the user.
    if not value:
        return
    if value.startswith("sb_secret_"):
        raise PrivateReportError("elevated credentials are not allowed")
    parts = value.split(".")
    if len(parts) == 3:
        try:
            claims = json.loads(base64.urlsafe_b64decode(parts[1] + "=" * (-len(parts[1]) % 4)))
        except (ValueError, UnicodeError):
            claims = None
        if isinstance(claims, dict) and claims.get("role") == "service_role":
            raise PrivateReportError("elevated credentials are not allowed")


def _private_body(response: Any, stage: str) -> Any:
    if not isinstance(response, HttpResponse) or type(response.status_code) is not int:
        raise PrivateReportError(f"{stage} response is invalid")
    if response.status_code != 200:
        raise PrivateReportError(f"{stage} request failed")
    body = response.body
    if isinstance(body, dict) and any(key in body for key in ("error", "error_description", "message", "code", "statusCode")):
        raise PrivateReportError(f"{stage} response is invalid")
    return body


_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")


def _require_safe_id(value: str, label: str) -> str:
    if not isinstance(value, str) or not _SAFE_ID.fullmatch(value):
        raise ValueError(f"{label} must be a safe task/run identifier")
    return value


def _require_header_value(value: str | None, label: str) -> str | None:
    if value is not None and not isinstance(value, str):
        raise ValueError(f"{label} must be a string")
    if value is not None and any(ord(char) < 0x20 or 0x7F <= ord(char) <= 0x9F for char in value):
        raise ValueError(f"{label} must not contain HTTP control characters")
    return value


def _require_base_url(value: str | None) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError("Supabase base_url must be a non-empty string")
    if any(ord(char) < 0x20 or 0x7F <= ord(char) <= 0x9F for char in value):
        raise ValueError("Supabase base_url must not contain control characters")
    return value


RequestFn = Callable[[str, str, Mapping[str, str], Mapping[str, Any] | None], Any]


@dataclass(frozen=True)
class SupabaseHttpTransport:
    base_url: str | None = None
    public_key: str | None = field(default=None, repr=False)
    access_token: str | None = field(default=None, repr=False)
    request_fn: RequestFn | None = None
    object_request_fn: RequestFn | None = None
    report_bucket: str = "reports"

    def _request(self, method: str, path: str, payload: Mapping[str, Any] | None = None,
                 *, request_fn: RequestFn | None = None) -> Any:
        # Validate supplied origins and header values before the configured
        # transport check. A malformed value must never be hidden behind the
        # generic "not configured" branch, even though no request is sent.
        base_url = _require_base_url(self.base_url) if self.base_url is not None else None
        _require_header_value(self.public_key, "public_key")
        _require_header_value(self.access_token, "access_token")
        sender = request_fn if request_fn is not None else self.request_fn
        if not base_url or not self.public_key or sender is None:
            raise HttpTransportNotConfigured("Supabase HTTP transport is not configured; no request was sent")
        try:
            parsed = urlparse(base_url)
        except ValueError as exc:
            raise ValueError("Supabase base_url must be a valid absolute HTTP(S) origin") from exc
        try:
            parsed.port
        except ValueError as exc:
            raise ValueError("Supabase base_url must use a valid port") from exc
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.path not in {"", "/"}
            or parsed.params
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("Supabase base_url must be an absolute HTTP(S) origin without credentials or query data")
        headers = {"apikey": self.public_key, "Content-Type": "application/json"}
        if path.startswith("/rest/v1/"):
            headers["Accept-Profile"] = "public"
            headers["Content-Profile"] = "public"
        if self.access_token:
            headers["Authorization"] = f"Bearer {self.access_token}"
        return sender(method, base_url.rstrip("/") + path, headers, payload)

    def auth_user(self) -> Any:
        if not self.access_token:
            raise ValueError("access_token is required for auth_user")
        return self._request("GET", "/auth/v1/user")

    def insert_task(self, task: Mapping[str, Any]) -> Any:
        return self._request("POST", "/rest/v1/tasks", task)

    def claim_tasks(self) -> Any:
        return self._request("GET", "/rest/v1/tasks?status=eq.pending&order=created_at.asc&limit=1")

    def read_report(self, task_id: str, run_id: str) -> Any:
        """Legacy metadata-only query; this does not download an object."""
        if not self.access_token:
            raise ValueError("access_token is required for private report reads")
        task_id = _require_safe_id(task_id, "task_id")
        run_id = _require_safe_id(run_id, "run_id")
        return self._request("GET", f"/rest/v1/task_runs?task_id=eq.{task_id}&run_id=eq.{run_id}&select=report_path")

    def read_report_content(self, task_id: str, run_id: str) -> dict[str, Any]:
        """Read a private JSON report using the same user token at every step.

        Requires both request_fn and object_request_fn explicitly; absence of
        either fails before even Auth is called. report_bucket is trusted wiring
        configuration, never metadata. report_path must be bucket-relative and
        exactly task_id/run_id/<ASCII filename>.json (no encoding/normalization).
        Returns {task_id, run_id, report_path, content}, where content is a JSON
        object. No signed/public URL, credential fallback, or HTTP client exists
        here. The deployed bucket must separately be verified private with RLS.
        """
        task_id = _require_safe_id(task_id, "task_id")
        run_id = _require_safe_id(run_id, "run_id")
        _require_safe_id(self.report_bucket, "report_bucket")
        _require_header_value(self.access_token, "access_token")
        _require_header_value(self.public_key, "public_key")
        if not self.access_token or not self.access_token.strip():
            raise ValueError("access_token is required for private report content")
        _reject_elevated_key(self.access_token)
        _reject_elevated_key(self.public_key)
        # User tokens must never be transmitted over an unencrypted origin.
        try:
            private_origin = urlparse(_require_base_url(self.base_url))
        except ValueError:
            raise PrivateReportError("private report origin is invalid") from None
        if private_origin.scheme != "https":
            raise PrivateReportError("private report origin requires HTTPS")
        if not callable(self.request_fn) or not callable(self.object_request_fn):
            raise HttpTransportNotConfigured("private report transports are not configured; no request was sent")

        def request_body(stage: str, path: str, sender: RequestFn) -> Any:
            try:
                response = self._request("GET", path, request_fn=sender)
            except Exception:
                # Never include transport exceptions, URLs, headers, or bodies.
                raise PrivateReportError(f"{stage} request failed") from None
            return _private_body(response, stage)

        user = request_body("auth", "/auth/v1/user", self.request_fn)
        if (not isinstance(user, dict) or not isinstance(user.get("id"), str)
                or not user["id"].strip() or user.get("role") != "authenticated"):
            raise PrivateReportError("auth response is invalid")
        rows = request_body("metadata", f"/rest/v1/task_runs?task_id=eq.{task_id}&run_id=eq.{run_id}"
                            "&select=task_id,run_id,report_path&limit=2", self.request_fn)
        if not isinstance(rows, list) or len(rows) != 1 or not isinstance(rows[0], dict):
            raise PrivateReportError("report is unavailable or unauthorized")
        row = _private_body(HttpResponse(200, rows[0]), "metadata")
        if row.get("task_id") != task_id or row.get("run_id") != run_id:
            raise PrivateReportError("report metadata binding is invalid")
        path = row.get("report_path")
        prefix = f"{task_id}/{run_id}/"
        if (not isinstance(path, str) or not path.startswith(prefix)
                or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}\.json", path[len(prefix):])):
            raise PrivateReportError("report object path is invalid")
        content = request_body("object", f"/storage/v1/object/authenticated/{self.report_bucket}/{path}",
                               self.object_request_fn)
        if isinstance(content, bytes):
            try:
                content = json.loads(content.decode("utf-8"))
            except (ValueError, UnicodeError):
                raise PrivateReportError("object response is invalid") from None
        content = _private_body(HttpResponse(200, content), "object")
        if not isinstance(content, dict) or not content:
            raise PrivateReportError("object response is invalid")
        if ("task_id" in content and content["task_id"] != task_id
                or "run_id" in content and content["run_id"] != run_id):
            raise PrivateReportError("report content binding is invalid")
        return {"task_id": task_id, "run_id": run_id, "report_path": path, "content": content}
