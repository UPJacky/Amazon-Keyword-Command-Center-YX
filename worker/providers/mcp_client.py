"""MCP Provider client with injected transport and tool discovery."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from worker.providers.base import ProviderContract
from worker.providers.mcp_protocol import find_tool, parse_tools_list, tools_list_request


class McpProvider(ProviderContract):
    provider_name = "mcp"

    def discover_tools(self, request_id: int = 1) -> list[dict[str, Any]]:
        response = self.fetch_jsonrpc(tools_list_request(request_id))
        return parse_tools_list(response)

    def fetch_jsonrpc(self, request: Mapping[str, Any]) -> Mapping[str, Any]:
        if self.transport is None:
            self.usage.failures += 1
            raise RuntimeError("MCP transport is not configured; no network request was made")
        response = self.fetch("jsonrpc", dict(request))
        if not isinstance(response, Mapping):
            raise ValueError("MCP response must be an object")
        return response

    def require_tool(self, tools: list[Mapping[str, Any]], name: str) -> dict[str, Any]:
        return find_tool(tools, name)

    def write_tools_snapshot(self, tools: list[Mapping[str, Any]], destination: str | Path) -> Path:
        path = Path(destination)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"provider": self.provider_name, "tools": tools}, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        return path
