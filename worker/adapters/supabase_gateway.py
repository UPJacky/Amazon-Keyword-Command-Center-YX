"""Transport-neutral Supabase gateway contract.

This module intentionally performs no network I/O. A production transport must
be injected after Auth, RLS and Storage have been validated in Supabase.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Protocol


class GatewayNotConfigured(RuntimeError):
    pass


SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")


def _require_safe_id(value: str, label: str) -> str:
    if not isinstance(value, str) or not SAFE_ID.fullmatch(value):
        raise ValueError(f"{label} must be a safe task/run identifier")
    return value


class SupabaseTransport(Protocol):
    def request(self, operation: str, payload: dict[str, Any]) -> Any: ...


@dataclass(frozen=True)
class SupabaseGateway:
    url: str | None = None
    transport: SupabaseTransport | None = None

    def _call(self, operation: str, payload: dict[str, Any]) -> Any:
        if not self.url or self.transport is None:
            raise GatewayNotConfigured("Supabase transport is not configured; no network request was made")
        return self.transport.request(operation, payload)

    def get_current_user(self, access_token: str) -> Any:
        if not access_token:
            raise ValueError("access token is required")
        return self._call("auth.get_current_user", {"access_token": access_token})

    def create_task(self, task: dict[str, Any]) -> Any:
        return self._call("tasks.create", task)

    def claim_pending_task(self, worker_id: str) -> Any:
        if not worker_id:
            raise ValueError("worker_id is required")
        return self._call("tasks.claim_pending", {"worker_id": worker_id})

    def save_config(self, config: dict[str, Any]) -> Any:
        return self._call("configs.save", config)

    def read_report(self, task_id: str, run_id: str, access_token: str) -> Any:
        if not access_token:
            raise ValueError("access token is required for private report reads")
        task_id = _require_safe_id(task_id, "task_id")
        run_id = _require_safe_id(run_id, "run_id")
        return self._call("reports.read_private", {"task_id": task_id, "run_id": run_id, "access_token": access_token})
