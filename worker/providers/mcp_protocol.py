"""MCP JSON-RPC tools/list contract without network transport."""

from __future__ import annotations

from typing import Any, Mapping


def tools_list_request(request_id: int = 1) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "method": "tools/list", "params": {}}


def parse_tools_list(response: Mapping[str, Any]) -> list[dict[str, Any]]:
    if response.get("jsonrpc") != "2.0":
        raise ValueError("invalid JSON-RPC version")
    if "error" in response:
        error = response["error"]
        raise RuntimeError(f"MCP tools/list failed: {error}")
    result = response.get("result")
    if not isinstance(result, Mapping) or not isinstance(result.get("tools"), list):
        raise ValueError("MCP tools/list response missing result.tools")
    tools: list[dict[str, Any]] = []
    for item in result["tools"]:
        if not isinstance(item, Mapping) or not isinstance(item.get("name"), str):
            raise ValueError("MCP tool entry missing name")
        tools.append(dict(item))
    return tools


def find_tool(tools: list[Mapping[str, Any]], name: str) -> dict[str, Any]:
    for tool in tools:
        if tool.get("name") == name:
            return dict(tool)
    raise KeyError(f"MCP tool not found: {name}")

