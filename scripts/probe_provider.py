"""Run an explicitly requested, bounded live MCP probe.

The script is intentionally separate from the offline UAT.  It reads
``XYDC_MCP_URL`` and ``XYDC_MCP_TOKEN`` only from the process environment,
does not print credentials or remote bodies, and writes evidence only to the
user-selected private output path.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Mapping

# When invoked as ``python scripts/probe_provider.py``, Python places the
# scripts directory—not the project root—on ``sys.path``.  Add the root so
# the probe works both as a script and as a module without changing imports.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from worker.providers.base import RetryPolicy
from worker.providers.mcp_client import McpProvider
from worker.providers.mcp_http_transport import McpHttpTransport, _safe_response_metadata


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Bounded live MCP tools/list probe")
    parser.add_argument("--output", required=True, help="private JSON evidence path; never commit it")
    parser.add_argument("--tool", help="optional confirmed tool name for one bounded sample call")
    parser.add_argument("--arguments-json", default="{}", help="JSON object for the optional sample call")
    return parser


def _write_evidence(path: Path, payload: dict[str, Any]) -> None:
    if path.exists() and path.is_symlink():
        raise RuntimeError("output path must not be a symlink")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    if temporary.exists() and temporary.is_symlink():
        raise RuntimeError("temporary output path must not be a symlink")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    temporary.replace(path)


def _response_metadata(provider: McpProvider) -> dict[str, str]:
    """Return only the transport's already-sanitized response metadata."""

    value = getattr(provider.transport, "last_response_metadata", {})
    return _safe_response_metadata(value)


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    endpoint = os.environ.get("XYDC_MCP_URL", "")
    token = os.environ.get("XYDC_MCP_TOKEN", "")
    if not endpoint or not token:
        print(json.dumps({"ok": False, "code": "MISSING_PROVIDER_CONFIG"}, ensure_ascii=False))
        return 2
    try:
        arguments = json.loads(args.arguments_json)
        if not isinstance(arguments, dict):
            raise ValueError("sample arguments must be an object")
        provider = McpProvider(
            McpHttpTransport(endpoint, token),
            retry_policy=RetryPolicy(max_retries=2, backoff_seconds=(1, 2)),
        )
        tools = provider.discover_tools()
        evidence: dict[str, Any] = {
            "provider": "xiyou-mcp",
            "tools": tools,
            "usage_after_tools_list": provider.usage.to_dict(),
            "response_metadata_after_tools_list": _response_metadata(provider),
        }
        if args.tool:
            provider.require_tool(tools, args.tool)
            sample_response = provider.fetch(args.tool, arguments)
            evidence["sample"] = {"tool": args.tool, "response": sample_response}
            evidence["usage_after_sample"] = provider.usage.to_dict()
            evidence["response_metadata_after_sample"] = _response_metadata(provider)
        _write_evidence(Path(args.output), evidence)
        summary = {
            "ok": True,
            "tool_count": len(tools),
            "tool_names": [tool.get("name") for tool in tools],
            "sample_requested": bool(args.tool),
            "usage": provider.usage.to_dict(),
            "response_metadata": _response_metadata(provider),
        }
        print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
        return 0
    except Exception:
        print(json.dumps({"ok": False, "code": "PROVIDER_PROBE_FAILED"}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    sys.exit(main())
