"""Bind the existing gateway's private-read operation to a user HTTP client.

Only report reads are implemented here. Worker claiming and config writes need
separate reviewed server endpoints; this adapter never substitutes a table read
for an atomic queue claim or an elevated credential for a normal user.
"""

from dataclasses import dataclass, replace
from typing import Any

from worker.adapters.supabase_gateway import GatewayNotConfigured
from worker.adapters.supabase_http import SupabaseHttpTransport


@dataclass(frozen=True)
class PrivateReportGatewayTransport:
    client: SupabaseHttpTransport

    def request(self, operation: str, payload: dict[str, Any]) -> Any:
        if operation != "reports.read_private":
            raise GatewayNotConfigured("operation is not implemented by the private report adapter")
        if not isinstance(payload, dict) or set(payload) != {"task_id", "run_id", "access_token"}:
            raise ValueError("private report request requires explicit task, run and user session")
        # Never inherit a previous caller's token from the configured template.
        client = replace(self.client, access_token=payload["access_token"])
        return client.read_report_content(payload["task_id"], payload["run_id"])
